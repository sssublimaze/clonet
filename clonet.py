#!/usr/bin/env python3

import shutil, pathlib, re, mimetypes, argparse
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

try:
    from tqdm import tqdm
    TQDM = True
except ImportError:
    TQDM = False

# ───────────────────── BANNER ─────────────────────

BANNER = """
     ▄████████  ▄█        ▄██████▄  ███▄▄▄▄      ▄████████     ███
    ███    ███ ███       ███    ███ ███▀▀▀██▄   ███    ███ ▀█████████▄
    ███    █▀  ███       ███    ███ ███   ███   ███    █▀     ▀███▀▀██
    ███        ███       ███    ███ ███   ███  ▄███▄▄▄         ███   ▀
    ███        ███       ███    ███ ███   ███ ▀▀███▀▀▀         ███
    ███    █▄  ███       ███    ███ ███   ███   ███    █▄      ███
    ███    ███ ███▌    ▄ ███    ███ ███   ███   ███    ███     ███
    ████████▀  █████▄▄██  ▀██████▀   ▀█   █▀    ██████████    ▄████▀
        ▀
                          [ by sssublimaze ]
"""

def exibir_banner():
    print(BANNER)

# ───────────────────── CLI ─────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Clone qualquer site com precisão pixel-perfect",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemplo: python clonet.py https://exemplo.com -m 2 -d 3"
    )
    parser.add_argument("url", nargs="?", help="URL do site para clonar")
    parser.add_argument("-o", "--output", help="Diretório de saída")
    parser.add_argument("-m", "--mode", type=int, choices=[1, 2, 3, 4],
                        help="Modo: 1=Landing, 2=Completo, 3=Frontend, 4=Turbo")
    parser.add_argument("-d", "--depth", type=int, default=0,
                        help="Profundidade máxima do crawling (0 = ilimitado)")
    parser.add_argument("--no-screenshot", action="store_true",
                        help="Não tirar screenshot")
    parser.add_argument("--no-banner", action="store_true",
                        help="Ocultar banner")
    return parser.parse_args()

# ───────────────────── UTILITÁRIOS ─────────────────────

def caminho_local(base_dir, url):
    parsed = urlparse(url)
    path = parsed.path.lstrip("/") or "index.html"
    p = base_dir / path
    if not p.suffix and not str(p).endswith(('.html', '.htm')):
        p = p / "index.html"
    elif not p.suffix:
        p = p.with_suffix('.html')
    return p


def salvar(arquivo, conteudo, binario=False):
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    if binario:
        arquivo.write_bytes(conteudo)
    else:
        arquivo.write_text(conteudo, encoding="utf-8", errors="ignore")


def is_same_domain(url, dominio):
    return urlparse(url).netloc == dominio

# ───────────────────── ASSETS ─────────────────────

def baixar_asset(session, url, base_dir, modo_frontend=False):
    try:
        if modo_frontend and any(ext in url.lower() for ext in
                                 ['.jpg', '.jpeg', '.png', '.gif', '.webp',
                                  '.mp4', '.avi', '.mov']):
            return urlparse(url).path.lstrip("/") or "asset"

        r = session.get(url, timeout=15)
        r.raise_for_status()

        path = base_dir / urlparse(url).path.lstrip("/")
        if not path.suffix:
            ext = mimetypes.guess_extension(r.headers.get("content-type", "")) or ".bin"
            path = path.with_suffix(ext)

        salvar(path, r.content, binario=True)
        return path.relative_to(base_dir).as_posix()
    except Exception:
        return urlparse(url).path.lstrip("/") or url


def baixar_assets_paralelo(session, urls, base_dir, modo_frontend, desc="📦 Assets"):
    if not urls:
        return {}
    mapping = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futuros = {executor.submit(baixar_asset, session, u, base_dir, modo_frontend): u for u in urls}
        iterador = as_completed(futuros)
        if TQDM:
            iterador = tqdm(iterador, total=len(urls), desc=desc, unit="asset")
        for futuro in iterador:
            u = futuros[futuro]
            try:
                mapping[u] = futuro.result()
            except Exception:
                mapping[u] = urlparse(u).path.lstrip("/") or u
    return mapping

# ───────────────────── CSS ─────────────────────

def processa_css(css, page_url, asset_map, session, base_dir, modo_frontend):
    def replace_url(match):
        asset = match.group(1).strip('"\' ')
        if not asset or asset.startswith("data:"):
            return match.group(0)
        abs_url = urljoin(page_url, asset) if "://" not in asset else asset

        if abs_url in asset_map:
            return f"url({asset_map[abs_url]})"

        if is_same_domain(abs_url, urlparse(page_url).netloc):
            local = baixar_asset(session, abs_url, base_dir, modo_frontend)
            asset_map[abs_url] = local
            return f"url({local})"
        return match.group(0)

    return re.sub(r"url\((.*?)\)", replace_url, css)


def processar_css_externo(caminho_arquivo, css_url, asset_map, session, base_dir, modo_frontend):
    try:
        css_texto = pathlib.Path(caminho_arquivo).read_text(encoding="utf-8", errors="ignore")
        css_modificado = processa_css(css_texto, css_url, asset_map,
                                       session, base_dir, modo_frontend)
        pathlib.Path(caminho_arquivo).write_text(css_modificado, encoding="utf-8")
    except Exception:
        pass

# ───────────────────── HTML ─────────────────────

def coletar_assets_tag(soup, page_url, dominio):
    urls = set()
    tags = {
        "img": ["src", "data-src", "data-lazy"],
        "script": ["src"],
        "link": ["href"],
        "source": ["src", "srcset"],
        "video": ["src"],
        "audio": ["src"],
        "iframe": ["src"],
    }
    for tag_name, attrs in tags.items():
        for tag in soup.find_all(tag_name):
            for attr in attrs:
                val = tag.get(attr)
                if not val:
                    continue
                if attr == "srcset":
                    for item in val.split(","):
                        url_part = item.strip().split()[0]
                        abs_url = urljoin(page_url, url_part)
                        if is_same_domain(abs_url, dominio):
                            urls.add(abs_url)
                else:
                    abs_url = urljoin(page_url, val)
                    if is_same_domain(abs_url, dominio):
                        urls.add(abs_url)
    return list(urls)


def reescreve_html(html, page_url, asset_map, session, base_dir, modo_frontend):
    soup = BeautifulSoup(html, "html.parser")

    for base in soup.find_all("base"):
        base.decompose()

    tags = {
        "img": ["src", "data-src", "data-lazy"],
        "script": ["src"],
        "link": ["href"],
        "source": ["src", "srcset"],
        "video": ["src"],
        "audio": ["src"],
        "iframe": ["src"],
    }

    for tag_name, attrs in tags.items():
        for tag in soup.find_all(tag_name):
            for attr in attrs:
                val = tag.get(attr)
                if not val:
                    continue
                if attr == "srcset":
                    partes = []
                    for item in val.split(","):
                        url_part = item.strip().split()[0]
                        abs_url = urljoin(page_url, url_part)
                        if abs_url in asset_map:
                            partes.append(item.replace(url_part, asset_map[abs_url]))
                        else:
                            partes.append(item)
                    tag[attr] = ", ".join(partes)
                else:
                    abs_url = urljoin(page_url, val)
                    if abs_url in asset_map:
                        tag[attr] = asset_map[abs_url]

    for style in soup.find_all("style"):
        if style.string:
            style.string = processa_css(style.string, page_url, asset_map,
                                        session, base_dir, modo_frontend)

    return str(soup)

# ───────────────────── INTERATIVO ─────────────────────

def perguntar_url():
    while True:
        url = input("\n🔗 Cole a URL do site para clonar: ").strip().rstrip("/")
        if url.startswith(("http://", "https://")):
            return url
        print("❌ URL inválida. Deve começar com http:// ou https://")


def menu_interativo():    
    print("=" * 60)
    print("1️⃣  Apenas Landing Page (mais rápido)")
    print("2️⃣  Site Completo (com crawling)")
    print("3️⃣  Frontend Apenas (HTML + CSS + JS, sem imagens)")
    print("4️⃣  Modo Turbo (HTML puro, sem assets externos)")
    print("=" * 60)
    while True:
        try:
            opcao = int(input("\nEscolha uma opção (1-4): "))
            if opcao in [1, 2, 3, 4]:
                return opcao
            print("❌ Escolha apenas entre 1, 2, 3 ou 4.")
        except ValueError:
            print("❌ Digite um número válido.")

# ───────────────────── MAIN ─────────────────────

def main():
    args = parse_args()

    if not args.no_banner:
        exibir_banner()

    url = args.url or perguntar_url()
    while not url.startswith(("http://", "https://")):
        print("❌ URL inválida.")
        url = perguntar_url()

    modo = args.mode or menu_interativo()

    DOMINIO = urlparse(url).netloc
    RAIZ = pathlib.Path(args.output or DOMINIO)

    if RAIZ.exists():
        shutil.rmtree(RAIZ)
    RAIZ.mkdir()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
    })

    modo_frontend = (modo == 3)
    modo_turbo = (modo == 4)
    crawl_completo = (modo == 2)
    landing = (modo == 1)
    depth_max = args.depth if args.depth > 0 else float('inf')

    labels = {1: "Landing Page", 2: "Site Completo", 3: "Frontend", 4: "Turbo"}
    print(f"\n- Modo: {labels[modo]}")
    print(f"- Salvando: {RAIZ.resolve()}")
    if crawl_completo:
        print(f"- Profundidade: {'ilimitada' if args.depth == 0 else args.depth}")

    fila = [(url, 0)]
    visitados = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1
        )

        pagina_atual = 0
        while fila:
            current_url, depth = fila.pop(0)
            if current_url in visitados:
                continue
            visitados.add(current_url)
            pagina_atual += 1

            print(f"\n📄 [{pagina_atual}] Clonando: {current_url}")

            try:
                page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                try:
                    page.goto(current_url, wait_until="load", timeout=60000)
                except Exception as e:
                    print(f"⚠️  Erro ao carregar: {e}")
                    continue

            if not modo_turbo and not modo_frontend:
                page.evaluate("""
                async () => {
                    await new Promise(r => {
                        let h = 0;
                        const interval = setInterval(() => {
                            window.scrollBy(0, 400);
                            h += 400;
                            if (h >= document.body.scrollHeight) {
                                clearInterval(interval);
                                r();
                            }
                        }, 120);
                    });
                }
                """)
                page.wait_for_timeout(1500)

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            asset_urls = coletar_assets_tag(soup, current_url, DOMINIO)

            if modo_frontend:
                asset_urls = [u for u in asset_urls if not any(
                    ext in u.lower() for ext in
                    ['.jpg', '.jpeg', '.png', '.gif', '.webp',
                     '.mp4', '.avi', '.mov']
                )]

            if modo_turbo:
                asset_map = {u: urlparse(u).path.lstrip("/") or u for u in asset_urls}
                print("   ⚡ Modo Turbo: assets mantidos nos URLs originais")
            else:
                qtd = len(asset_urls)
                print(f"   📦 Baixando {qtd} assets..." if qtd else "   📦 Nenhum asset para baixar")
                asset_map = baixar_assets_paralelo(session, asset_urls, RAIZ, modo_frontend)

            html_modificado = reescreve_html(html, current_url, asset_map,
                                              session, RAIZ, modo_frontend)

            local_path = caminho_local(RAIZ, current_url)
            salvar(local_path, html_modificado)

            if not modo_turbo:
                for url_css in asset_urls:
                    if url_css.endswith('.css'):
                        css_local = RAIZ / urlparse(url_css).path.lstrip("/")
                        if css_local.exists():
                            processar_css_externo(str(css_local), url_css,
                                                  asset_map, session, RAIZ, modo_frontend)

            if not modo_turbo and not args.no_screenshot:
                try:
                    screenshot_path = str(local_path).replace(".html", "") + "_preview.png"
                    page.screenshot(path=screenshot_path, full_page=True)
                except Exception:
                    pass

            if crawl_completo and depth < depth_max:
                links = page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href)"
                )
                for link in links:
                    if link.startswith("http") and DOMINIO in link and link not in visitados:
                        fila.append((link, depth + 1))

            if landing or modo_turbo:
                break

        browser.close()

    print(f"\n{'═' * 50}")
    print(f"✅ CLONE FINALIZADO!")
    print(f"📁 Pasta: {RAIZ.resolve()}")
    print(f"🔢 Páginas clonadas: {len(visitados)}")
    print(f"{'═' * 50}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Operação cancelada pelo usuário.")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")

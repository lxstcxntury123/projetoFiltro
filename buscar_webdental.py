import sys
import time
import unicodedata
import re
import json
import os
import requests
from bs4 import BeautifulSoup
from thefuzz import fuzz

URL_BUSCA = "https://sistema.webdentalsolucoes.io/paciente/paciente_geral_sql.php"
URL_REFERER = "https://sistema.webdentalsolucoes.io/paciente/paciente_geral.php?procurapaciente=odontograma"
ARQUIVO_COOKIES = "cookies_webdental.json"

SIMILARIDADE_MINIMA = 85
PAUSA = 1.2

def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).upper().strip()

def carregar_cookies() -> dict:
    if not os.path.exists(ARQUIVO_COOKIES):
        print(f"\n Arquivo '{ARQUIVO_COOKIES}' nao encontrado!")
        print()
        print("=" * 55)
        print("  COMO EXPORTAR OS COOKIES (1 minuto so):")
        print("=" * 55)
        print()
        print("  1. Abra o Chrome e acesse o WebDental logado")
        print()
        print("  2. Instale a extensao gratuita 'Cookie-Editor':")
        print("     https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm")
        print()
        print("  3. Com o WebDental aberto, clique no icone")
        print("     da extensao (canto superior direito do Chrome)")
        print()
        print("  4. Clique em 'Export' (icone de seta para baixo)")
        print("     -> 'Export as JSON'")
        print()
        print(f"  5. Salve como '{ARQUIVO_COOKIES}'")
        print(f"     NA MESMA PASTA deste script")
        print()
        print("  6. Rode o script novamente")
        print("=" * 55)
        sys.exit(1)

    try:
        with open(ARQUIVO_COOKIES, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Arquivo de cookies invalido (nao e JSON valido): {e}")
        sys.exit(1)

    if isinstance(dados, list):
        cookies = {c["name"]: c["value"] for c in dados if "name" in c and "value" in c}
    elif isinstance(dados, dict):
        cookies = dados
    else:
        print("Formato de cookies nao reconhecido.")
        sys.exit(1)

    if not cookies:
        print("Nenhum cookie encontrado no arquivo. Tente exportar novamente.")
        sys.exit(1)

    print(f"OK  {len(cookies)} cookies carregados com sucesso")
    return cookies

def buscar_paciente(nome: str, session: requests.Session) -> list[str]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": URL_REFERER,
        "Origin": "https://sistema.webdentalsolucoes.io",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    payload = {
        "queryString": nome,
        "colunasOcultar": "",
    }

    try:
        resp = session.post(URL_BUSCA, data=payload, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"      ERRO na requisicao: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    nomes_encontrados = []
    
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if tds:
            nome_celula = tds[0].get_text(separator=" ", strip=True)
            if nome_celula and len(nome_celula) > 3 and nome_celula.upper() != "PACIENTE":
                nomes_encontrados.append(nome_celula)

    return nomes_encontrados

def verificar_match(nome_buscado: str, nomes_retornados: list[str]) -> tuple[bool, str, int]:
    n_buscado = normalizar(nome_buscado)
    melhor_score = 0
    melhor_nome  = ""

    for nome_ret in nomes_retornados:
        n_ret = normalizar(nome_ret)
        score = max(
            fuzz.token_sort_ratio(n_buscado, n_ret),
            fuzz.partial_ratio(n_buscado, n_ret),
        )
        if score > melhor_score:
            melhor_score = score
            melhor_nome  = nome_ret

    encontrou = melhor_score >= SIMILARIDADE_MINIMA
    return encontrou, melhor_nome, melhor_score

def testar_sessao(session: requests.Session) -> bool:
    try:
        resp = session.get(URL_REFERER, timeout=10, allow_redirects=True)
        if "index.php" in resp.url and "login" in resp.url.lower():
            return False
        return resp.status_code == 200
    except Exception:
        return False

def main():
    print()
    print("=" * 55)
    print("   BUSCADOR WEBDENTAL - REQUESTS PURO")
    print("=" * 55)
    print()
    print("  Cole os nomes abaixo (um por linha).")
    print("  Quando terminar: ENTER -> Ctrl+Z -> ENTER")
    print()

    try:
        entrada = sys.stdin.read().splitlines()
    except EOFError:
        entrada = []

    lista_nomes = [n.strip() for n in entrada if n.strip()]

    if not lista_nomes:
        print("Nenhum nome recebido. Encerrando.")
        sys.exit(0)

    print(f"\n{len(lista_nomes)} nomes recebidos.")
    print("Carregando cookies...\n")

    cookies = carregar_cookies()
    session = requests.Session()
    session.cookies.update(cookies)

    print("Verificando sessao no WebDental...")
    if testar_sessao(session):
        print("Sessao valida — iniciando buscas!\n")
    else:
        print("\nSESSAO EXPIRADA ou invalida.")
        print(f"Acesse o WebDental, faca login, exporte os cookies novamente")
        print(f"e substitua o arquivo '{ARQUIVO_COOKIES}'.\n")
        resposta = input("Continuar mesmo assim? (s/n): ").strip().lower()
        if resposta != "s":
            sys.exit(0)
        print()

    encontrados = []
    nao_encontrados = []

    print("-" * 55)

    for i, nome in enumerate(lista_nomes, 1):
        print(f"[{i:>3}/{len(lista_nomes)}] {nome}")

        nomes_retornados = buscar_paciente(nome, session)
        achou, melhor, score = verificar_match(nome, nomes_retornados)

        if achou:
            exato = normalizar(nome) == normalizar(melhor)
            tag = "EXATO" if exato else f"SIMILAR {score}%"
            print(f"            -> [{tag}] {melhor}")
            encontrados.append((nome, melhor, score))
        else:
            if melhor:
                print(f"            -> NAO ENCONTRADO (proximo: '{melhor}' — {score}%)")
            else:
                print(f"            -> NAO CONSTA NO SISTEMA")
            nao_encontrados.append(nome)

        time.sleep(PAUSA)

    print()
    print("=" * 55)
    print("   RELATORIO FINAL")
    print("=" * 55)

    print(f"\nJA PASSOU / AGENDOU ({len(encontrados)}):")
    if encontrados:
        for nome_original, nome_sistema, score in encontrados:
            print(f"  + {nome_original}")
    else:
        print("  (nenhum)")

    print(f"\nNAO ENCONTRADOS ({len(nao_encontrados)}):")
    if nao_encontrados:
        for nome in nao_encontrados:
            print(f"  - {nome}")
    else:
        print("  (nenhum)")

    print()
    print("=" * 55)
    print(f"  Total: {len(lista_nomes)} | Encontrados: {len(encontrados)} | Nao encontrados: {len(nao_encontrados)}")
    print("=" * 55)
    print()


if __name__ == "__main__":
    main()
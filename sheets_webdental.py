import sys
import time
import unicodedata
import re
import json
import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from thefuzz import fuzz
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SHEET_ID = "106na5LyAuI_JlhVRq5w5DlPQq3B6tC6Ce9ZgLZts3GU"
SHEET_NAME = "LISTAGEM MÉDICA"

COL_DATA   = 3
COL_NOME   = 4
COL_STATUS = 8

STATUS_ALVO = "JÁ PASSOU/AGENDOU"

URL_BUSCA   = "https://sistema.webdentalsolucoes.io/paciente/paciente_geral_sql.php"
URL_REFERER = "https://sistema.webdentalsolucoes.io/paciente/paciente_geral.php?procurapaciente=odontograma"
ARQUIVO_COOKIES = "cookies_webdental.json"

ARQUIVO_CREDENCIAIS = "credenciais_google.json"
ARQUIVO_TOKEN       = "token_google.json"
ESCOPOS = ["https://www.googleapis.com/auth/spreadsheets"]

SIMILARIDADE_MINIMA = 85
PAUSA = 1.2

def autenticar_google():
    if not os.path.exists(ARQUIVO_CREDENCIAIS):
        print(f"\nArquivo '{ARQUIVO_CREDENCIAIS}' não encontrado!")
        print("Siga o README para baixar as credenciais do Google Cloud.")
        sys.exit(1)

    creds = None

    if os.path.exists(ARQUIVO_TOKEN):
        creds = Credentials.from_authorized_user_file(ARQUIVO_TOKEN, ESCOPOS)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Renovando token do Google...")
            creds.refresh(Request())
        else:
            print("\nAbrindo navegador para autorização do Google Sheets...")
            print("(Isso só acontece na primeira vez)\n")
            flow = InstalledAppFlow.from_client_secrets_file(ARQUIVO_CREDENCIAIS, ESCOPOS)
            creds = flow.run_local_server(port=0)

        with open(ARQUIVO_TOKEN, "w") as f:
            f.write(creds.to_json())
        print(f"Token salvo em '{ARQUIVO_TOKEN}' — próximas execuções serão automáticas.\n")

    client = gspread.authorize(creds)
    aba = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    print(f"Conectado à planilha: {SHEET_NAME}")
    return aba

def pedir_data() -> str:
    print("\nQual data deseja processar?")
    print("  Exemplos: 15/04/2026  ou  15/04  (ano atual assumido)\n")
    entrada = input("  Data: ").strip()

    partes = entrada.split("/")
    if len(partes) == 2:
        entrada = f"{partes[0].zfill(2)}/{partes[1].zfill(2)}/{datetime.now().year}"
    elif len(partes) == 3:
        entrada = f"{partes[0].zfill(2)}/{partes[1].zfill(2)}/{partes[2]}"
    else:
        print("Formato inválido. Use dd/mm/aaaa")
        sys.exit(1)

    try:
        datetime.strptime(entrada, "%d/%m/%Y")
    except ValueError:
        print(f"Data inválida: {entrada}")
        sys.exit(1)

    return entrada

def buscar_linhas_por_data(aba, data_alvo: str) -> list[tuple[int, str]]:
    print(f"\nFiltrando linhas com data {data_alvo}...")
    todos = aba.get_all_values()
    linhas = []

    for i, linha in enumerate(todos):
        num = i + 1
        if len(linha) < COL_DATA:
            continue
        if not linha[COL_DATA - 1].startswith(data_alvo):
            continue
        if len(linha) < COL_NOME or not linha[COL_NOME - 1].strip():
            continue
        nome = linha[COL_NOME - 1].strip()
        status = linha[COL_STATUS - 1].strip() if len(linha) >= COL_STATUS else ""
        if status:
            continue
        linhas.append((num, nome))

    print(f"  {len(linhas)} pacientes sem status encontrados para processar.")
    return linhas

def marcar_status(aba, numero_linha: int):
    aba.update_cell(numero_linha, COL_STATUS, STATUS_ALVO)

def carregar_cookies() -> dict:
    if not os.path.exists(ARQUIVO_COOKIES):
        print(f"\nArquivo '{ARQUIVO_COOKIES}' não encontrado!")
        print("Abra o Chrome, acesse o WebDental logado.")
        print("F12 > Application > Cookies > copie PHPSESSID e _ugeuid")
        print(f"Salve no arquivo '{ARQUIVO_COOKIES}' como: {{\"PHPSESSID\": \"...\", \"_ugeuid\": \"...\"}}")
        sys.exit(1)

    with open(ARQUIVO_COOKIES, "r", encoding="utf-8") as f:
        dados = json.load(f)

    if isinstance(dados, list):
        cookies = {c["name"]: c["value"] for c in dados if "name" in c}
    else:
        cookies = dados

    print(f"Cookies carregados ({len(cookies)} cookies)")
    return cookies

def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).upper().strip()

def buscar_paciente(nome: str, session: requests.Session) -> list[str]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": URL_REFERER,
        "Origin": "https://sistema.webdentalsolucoes.io",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    }
    try:
        resp = session.post(URL_BUSCA, data={"queryString": nome, "colunasOcultar": ""}, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"      Erro na requisição: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    nomes = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if tds:
            celula = tds[0].get_text(separator=" ", strip=True)
            if celula and len(celula) > 3 and celula.upper() != "PACIENTE":
                nomes.append(celula)
    return nomes

def verificar_match(nome_buscado: str, nomes_retornados: list[str]) -> tuple[bool, str, int]:
    n = normalizar(nome_buscado)
    melhor_score, melhor_nome = 0, ""
    for nome_ret in nomes_retornados:
        score = max(fuzz.token_sort_ratio(n, normalizar(nome_ret)),
                    fuzz.partial_ratio(n, normalizar(nome_ret)))
        if score > melhor_score:
            melhor_score, melhor_nome = score, nome_ret
    encontrou = melhor_score >= SIMILARIDADE_MINIMA
    return encontrou, melhor_nome, melhor_score

def testar_sessao(session: requests.Session) -> bool:
    try:
        resp = session.get(URL_REFERER, timeout=10, allow_redirects=True)
        return resp.status_code == 200 and "index.php" not in resp.url
    except Exception:
        return False

def main():
    print()
    print("=" * 55)
    print("   FILTRAGEM 2.0")
    print("   Patch: Cadastro automático")
    print("=" * 55)

    aba = autenticar_google()
    data_alvo = pedir_data()
    linhas = buscar_linhas_por_data(aba, data_alvo)

    if not linhas:
        print("\nNenhuma linha para processar. Encerrando.")
        return

    print(f"\n{len(linhas)} pacientes para processar.")
    input("Pressione ENTER para iniciar (Ctrl+C para cancelar)...")

    cookies = carregar_cookies()
    session = requests.Session()
    session.cookies.update(cookies)

    print("\nVerificando sessão WebDental...")
    if testar_sessao(session):
        print("Sessão válida!\n")
    else:
        print("Sessão pode ter expirado. Verifique os cookies.")
        resp = input("Continuar mesmo assim? (s/n): ").strip().lower()
        if resp != "s":
            sys.exit(0)

    encontrados = nao_encontrados = erros = 0

    print("-" * 55)

    for i, (num_linha, nome) in enumerate(linhas, 1):
        print(f"[{i:>3}/{len(linhas)}] Linha {num_linha:>5} | {nome}")

        nomes_ret = buscar_paciente(nome, session)
        achou, melhor, score = verificar_match(nome, nomes_ret)

        if achou:
            tag = "EXATO" if normalizar(nome) == normalizar(melhor) else f"SIMILAR {score}%"
            print(f"           [{tag}] {melhor}")
            try:
                marcar_status(aba, num_linha)
                print(f"           Planilha atualizada -> {STATUS_ALVO}")
                encontrados += 1
            except Exception as e:
                print(f"           Erro ao atualizar planilha: {e}")
                erros += 1
        else:
            candidato = f" (mais próximo: '{melhor}' {score}%)" if melhor else ""
            print(f"           Nao encontrado{candidato}")
            nao_encontrados += 1

        time.sleep(PAUSA)

    print()
    print("=" * 55)
    print("   RELATÓRIO FINAL")
    print("=" * 55)
    print(f"  Total processado : {len(linhas)}")
    print(f"  Encontrados      : {encontrados}  -> '{STATUS_ALVO}'")
    print(f"  Não encontrados  : {nao_encontrados}")
    print(f"  Erros de escrita : {erros}")
    print("=" * 55)


if __name__ == "__main__":
    main()
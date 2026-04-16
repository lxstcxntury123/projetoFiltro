projetoFiltro, é um filtrador que fazer interligação entre o sistema WebDental (Legado) com a planilhas Sheets. Onde automatiza processos de registro de informações, utilizando cookies e OAuth 2 do Google

# INSTRUÇÕES DE USO

Versão base: buscar_webdental.py
Versão atualizada: sheets_webdental.py

Para usar ambos arquivos é necessário ter:
- Python 3.12+
- Instalar as depedências em requirements2.txt (1)
- Apagar o arquivo token_google.json (2)*
- Alterar o arquvo cookies_webdental.json para sua sessão atual (3)*

Logo após você pode executar diretamente pelo arquivo, ou, via Windowns PowerShell (recomendado)

1. Rode a seguinte linha de comando no terminal PowerShell:
pip install -r requeriments2.txt

2. Imperativo que pratique isso antes de iniciar o programa, pois, o token é apenas temporário onde é disponibilizado o acesso a planilha sheets.

3. Você deve alterar o valor de "PHPSESSID". Para conseguir o novo id acesse:
https://sistema.webdentalsolucoes.io/paciente/paciente_geral.php?procurapaciente=odontograma
Pressione F12, vá em Storage (Armazenamento), clique na sessão cookies, selecione a url, sessão, copie o valor de PHPSESSID e depois adicione em cookies_webdental.json

*. Processo que deve ser feito rotineiramente

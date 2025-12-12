import sys
import subprocess

# --- Configurações dos Novos Autores (Mantidas como Strings Normais) ---
# Seus e-mails e nomes reais
AUTHOR_LV16 = "Lv16 <lohran.hps@gmail.com>"
AUTHOR_GABRIEL = "gabrielandrade131 <gabrielandrade131@gmail.com>"

# Mapeamento: { SHA_parcial: [Nova Mensagem (em bytes), Autor_ID] }
# Garantindo que todas as mensagens são B'string'
COMMIT_MAP = {
    # Inicializações (Initial)
    b"f4f3641": [b"chore: Initial commit - Ready project structure", "backend"],
    b"0240163": [b"chore: Initial commit", "backend"],
    b"05b84ef": [b"chore: Initial commit - Ready project structure", "backend"],
    b"134124d": [b"chore: First commit", "backend"],

    # Front-end (Lv16)
    b"7e6f109": [b"refactor(rdo): Restore RDO wrapper + apply RDO prefill changes", "frontend"],
    b"33beb5d": [b"fix: Restore rdo.html wrapper including rdo_page.html to fix TemplateDoesNotExist", "frontend"],
    b"6080e48": [b"refactor(css): Refactor CSS layout and adjust margins in style.css and update db.sqlite3", "frontend"],
    b"49107f4": [b"refactor(js): Refactor notifications and AJAX requests to use standardized fetchJson and NotificationManager", "frontend"],
    b"58f7287": [b"refactor(js): Remove console.log statements and replace with NotificationManager.show for error handling", "frontend"],
    b"15c4ce4": [b"feat: Add pagination link preservation and filter display improvements in lista_servicos and home.html", "frontend"],
    b"daa050e": [b"feat: Add drawer navigation menu, update header and main layout, views and templates for OS CRUD", "frontend"],
    b"db0be88": [b"feat: Add logout overlay and update views.py to handle status_operacao changes", "frontend"],
    b"d282b2e": [b"refactor(ui): Refactor loading animation, update CSS, JS, and HTML templates to match new design", "frontend"],
    b"4bd729c": [b"feat: Add id attributes to select fields; implement JS prefill and disable fields based on OS existente selection", "frontend"],
    b"f595c03": [b"refactor(ui): Refactor loading screen to use DVD Loading Animation", "frontend"],
    b"b18b19e": [b"refactor(filters): Refactor filter panel and date range functionality in home page", "frontend"],
    b"2c18793": [b"feat: Add filter chip functionality for date range and improve filter clearing logic", "frontend"],
    b"7eb4fc2": [b"feat: Add filter panel and functionality to clear filters on home page", "frontend"],
    b"6559c99": [b"refactor(css/html): Refactor CSS and HTML files: update style.css and home.html templates, and modify database file", "frontend"],
    b"367eebe": [b"feat: Add event listeners for filter panel and data range bar toggles", "frontend"],
    b"00d56ac": [b"style: Add relative positioning to main and aside elements", "frontend"],
    b"bbcb65f": [b"feat: Add links to cadastro views in home.html and update urls.py", "frontend"],
    b"5a229da": [b"feat: Add date range filtering functionality with toggle button and form", "frontend"],
    b"7f64c5b": [b"refactor(ui): Refactor filter panel in home.html and style.css to modern design", "frontend"],
    b"c15fb8b": [b"chore: Update scripts.js with new service list; update database and setup files", "frontend"],
    b"0883b50": [b"refactor(css): Refactor CSS styles for GO application", "frontend"],
    b"8bc9a6f": [b"feat: Add loading screen, logout overlay, and notification system to the application", "frontend"],
    b"77a2341": [b"refactor(login): Refactor login page CSS and HTML; update image, database, and setup files", "frontend"],
    b"c7909e1": [b"feat: Create and style the login screen and specific modifications on the homepage", "frontend"],
    b"99bf4c8": [b"style: Update CSS (remove form legend border) and change navigation icon in home.html", "frontend"],
    b"afac874": [b"style: Update CSS styles and HTML templates for GO project", "frontend"],
    b"0a9213e": [b"refactor(ui): Refactor CSS and HTML files for improved layout and design", "frontend"],
    b"f4f42af": [b"feat: Update styles and functionality in GO application", "frontend"],
    b"a726a47": [b"refactor(css): Refactor CSS styles for buttons in style.css and update home.html", "frontend"],
    b"795aab0": [b"refactor(search): Refactor search form and add filter functionality", "frontend"],
    b"0a84388": [b"refactor(search): Refactor search functionality in OrdemServico views and templates; update styles in style.css and home.html", "frontend"],
    b"9ba1769": [b"feat: Add pagination controls and search functionality to the home page", "frontend"],
    b"8cc5071": [b"refactor(js): Refactor JavaScript code in scripts.js; update home.html with new data bindings and API calls", "frontend"],
    b"e70b04b": [b"refactor(ui): Refactor CSS and HTML templates; add JS filtering by status; modify Django form fields", "frontend"],
    b"3e19eb2": [b"feat: Table Integrations and Table Button Modal Layout", "frontend"],
    b"92eb006": [b"style: Layout update", "frontend"],
    b"9f176b0": [b"feat: Fetch Creation of a new column and layout updates", "frontend"],
    b"1aca816": [b"feat: Fetch Creation of a new column and layout updates", "frontend"],
    b"ced96f0": [b"feat: Fetch: layout update in table and menu", "frontend"],

    # Back-end / Outros (gabrielandrade131)
    b"ac60b0e": [b"fix: Update .gitignore: ignore venv_new; remove venv from index", "backend"],
    b"f44aee5": [b"fix: Update .gitignore: ignore fotos_rdo and DBs; remove sensitive files from index", "backend"],
    b"d3706d7": [b"fix: Remove fotos_equipamento from index; update .gitignore", "backend"],
    b"6c9b4df": [b"fix: Remove DBs and photos from index; update .gitignore", "backend"],
    b"4edcb2b": [b"migrations: Add 0091 - alter rdoatividade atividade field", "backend"],
    b"44b1859": [b"fix(search): Improve PO fallback - get first OS with non-empty/non-hyphen PO", "backend"],
    b"2c79143": [b"feat: Safe icontains for SQLite dev (Python-side accent-insensitive filtering)", "backend"],
    b"fe83d66": [b"feat: Safe icontains for SQLite dev (Python-side accent-insensitive filtering)", "backend"],
    b"37ff9ec": [b"feat: Make filters accent-insensitive when possible; fallback safe_icontains for non-Postgres DBs", "backend"],
    b"2f878f1": [b"deploy: Add observed hosts to ALLOWED_HOSTS", "backend"],
    b"9cc44ba": [b"deploy: Fix filters and ALLOWED_HOSTS", "backend"],
    b"8ba56d4": [b"fix(forms): Remove debug print statements from OrdemServicoForm", "backend"],
    b"8123dff": [b"chore: Update GO project files with various changes", "backend"],
    b"7390d0": [b"chore: Update Django project files: models, templates, and settings", "backend"],
    b"75e3d54": [b"feat: Add 'materiais_equipamentos' field to OS model; update views and frontend handling", "backend"],
    b"e4ec82c": [b"refactor(forms): Refactor OrdemServicoForm to use unique OS numbers in choices and os_objects dictionary", "backend"],
    b"1c3ca4f": [b"feat: Add export to PDF functionality for OS details", "backend"],
    b"eb83474": [b"chore: Update various files in the GO project", "backend"],
    b"daa798e": [b"chore: Update GO project files: various changes to scripts, templates, and database", "backend"],
    b"5db7cbe": [b"fix(auth): Remove ModelBackend from AUTHENTICATION_BACKENDS in setup/settings.py", "backend"],
    b"0fbf87b": [b"feat: Add new filter for coordinator in home view; update templates and models accordingly", "backend"],
    b"497ef75": [b"feat: Add new models and views for user, client and unit registration; update templates and CSS", "backend"],
    b"bcac5e2": [b"feat: Add functionality to export table to Excel; update templates and views", "backend"],
    b"6781dc": [b"feat: Add new field 'metodo_secundario' to OrdemServico model and related views and templates", "backend"],
    b"b7b935c": [b"fix: Fix observations", "backend"],
    b"2907270": [b"refactor(models): Refactor OrdemServico model and views to use URLField for new fields; update forms and templates", "backend"],
    b"24ca204": [b"fix: Fix forms, models, and html", "backend"],
    b"655b5f3": [b"feat: Add models", "backend"],
    b"2b33c34": [b"feat: Add new fields to OrdemServico model; update views, templates, and filter panel", "backend"],
    b"e17e637": [b"fix: Fix in models", "backend"],
    b"e9c659b": [b"fix: Forms", "backend"],
    b"cfe7a69": [b"fix: Models", "backend"],
    b"831d4aa": [b"fix(models): Update models.py to allow tag field to be blank and null", "backend"],
    b"64ab03c": [b"chore: Update various files (compiled Python, templates, database)", "backend"],
    b"debaf16": [b"fix: Fix models", "backend"],
    b"254d078": [b"feat: Add service association with tag", "backend"],
    b"f2e365e": [b"fix: Fix models", "backend"],
    b"523a8a2": [b"fix: Fix models.py", "backend"],
    b"8562aed": [b"fix: Fix models", "backend"],
    b"0f38aea": [b"fix: Fix error in forms", "backend"],
    b"d27fe34": [b"feat: Add client list", "backend"],
    b"3c8605e": [b"feat(models): Add client list, services, and tags", "backend"],
    b"480547a": [b"chore: Update code with various changes to templates, views, and JavaScript files", "backend"],
    b"bf7e9cf": [b"feat: Implement Work Order (WO) editing and search features with new routes, methods, and editing modal", "backend"],
    b"39976d9": [b"feat: Add status_comercial field to OrdemServicoForm; update details view, JS and HTML", "backend"],
    b"46b2a8d": [b"refactor(forms): Refactor OrdemServicoForm to use primary key for OS selection; streamline form submission", "backend"],
    b"913f93c": [b"refactor(forms/models): Refactor OrdemServicoForm, update models.py, and modify JS/HTML to reflect changes", "backend"],
    b"d9d722d": [b"fix: Changing models", "backend"],
    b"85b9cb6": [b"fix: Changing models", "backend"],
    b"4b070b0": [b"refactor(forms): Refactor OrdemServicoForm and related code to improve functionality and remove redundant code", "backend"],
    b"f710a7f": [b"refactor(forms/models): Refactor OrdemServicoForm, update models, templates, and views", "backend"],
    b"afce82a": [b"feat: Add functionality to select existing OS in OrdemServicoForm; update templates, JS, and forms.py", "backend"],
    b"fa0aff1": [b"refactor(forms): Refactor OrdemServicoForm to include OS type selection; update views and templates", "backend"],
    b"3169bd3": [b"fix: Fix models", "backend"],
    b"e797b0c": [b"fix: Fix models", "backend"],
    b"66374bd": [b"feat: Add new endpoint for OS details and update template to display additional information", "backend"],
    b"8411967": [b"refactor: Refactor views and templates for creating and listing order services", "backend"],
    b"2d0a6b4": [b"refactor: Refactor OrdemServico model and views, update templates and URLs for new functionality", "backend"],
    b"e858244": [b"chore: Update various files in the GO project", "backend"],
    b"62f5956": [b"fix: Fix syntax error in views", "backend"],
    b"bb46952": [b"feat: Creating forms", "backend"],
    b"e767dd5": [b"fix: Fix some bugs", "backend"],
    b"640a000": [b"feat: Add 2 models", "backend"],
}

def rewrite_commit(commit):
    """Função chamada pelo git-filter-repo para cada commit."""
    # Obter o SHA-1 abreviado para pesquisa
    sha_abbr = commit.original_id[:7]
    
    # Tenta encontrar o mapeamento
    if sha_abbr in COMMIT_MAP:
        new_message, author_id = COMMIT_MAP[sha_abbr]

        # 1. Mudar a Mensagem (Já é bytes, ok)
        commit.message = new_message
        
        # 2. Mudar o Autor
        if author_id == "frontend":
            new_author = AUTHOR_LV16
        elif author_id == "backend":
            new_author = AUTHOR_GABRIEL
        else:
            new_author = None 

        if new_author:
            # Separar o nome e email (e remover o >)
            name_str, email_str = new_author.split(" <")
            email_str = email_str[:-1]

            # CONVERSÃO ESSENCIAL: Garante que nome e e-mail são BYTES (utf-8)
            commit.author_name = name_str.encode('utf-8')
            commit.author_email = email_str.encode('utf-8')
            
            # O committer é definido igual ao autor
            commit.committer_name = commit.author_name
            commit.committer_email = commit.author_email
        
    return commit

if __name__ == '__main__':
    pass
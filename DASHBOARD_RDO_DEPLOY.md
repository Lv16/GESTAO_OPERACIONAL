# 🚀 GUIA DE INSTALAÇÃO E DEPLOYMENT - Dashboard RDO

## 📦 Arquivos para Deploy

Copie os seguintes arquivos para o servidor:

### 1. Backend (Backend Views)
```bash
# Copiar arquivo de views expandido
cp GO/dashboard_views.py <destino>/GO/dashboard_views.py

# Este arquivo será sobrescrito, então certifique-se de fazer backup
# Ele contém as 10 novas funções de API
```

### 2. Frontend (Template HTML)
```bash
# Copiar template do dashboard
cp GO/templates/dashboard_rdo.html <destino>/GO/templates/dashboard_rdo.html
```

### 3. JavaScript (Lógica de Cliente)
```bash
# Copiar arquivo JavaScript de dashboard
cp static/js/dashboard_rdo.js <destino>/static/js/dashboard_rdo.js
```

### 4. URLs (Configuração de Rotas)
```bash
# Atualizar arquivo de URLs
# Certifique-se de que as seguintes rotas foram adicionadas em setup/urls.py:
# - /api/rdo-dashboard/hh_confinado_por_dia/
# - /api/rdo-dashboard/hh_fora_confinado_por_dia/
# - /api/rdo-dashboard/ensacamento_por_dia/
# - /api/rdo-dashboard/tambores_por_dia/
# - /api/rdo-dashboard/residuos_liquido_por_dia/
# - /api/rdo-dashboard/residuos_solido_por_dia/
# - /api/rdo-dashboard/liquido_por_supervisor/
# - /api/rdo-dashboard/solido_por_supervisor/
# - /api/rdo-dashboard/volume_por_tanque/
# - /dashboard/rdo/
```

---

## ✅ Checklist de Instalação

### Pré-requisitos
- [ ] Django 4.0+ (seu projeto já tem)
- [ ] Python 3.8+ (seu projeto já tem)
- [ ] Acesso ao servidor
- [ ] Banco de dados com dados de RDO

### Passos de Instalação

#### 1. Backup
```bash
cd /var/www/html/GESTAO_OPERACIONAL

# Fazer backup dos arquivos originais
cp GO/dashboard_views.py GO/dashboard_views.py.bak.$(date +%s)
cp setup/urls.py setup/urls.py.bak.$(date +%s)
```

#### 2. Copiar Novos Arquivos
```bash
# Copiar files do repo/local para o servidor
# (ajuste os caminhos conforme necessário)

cp /caminho/local/GO/dashboard_views.py ./GO/
cp /caminho/local/GO/templates/dashboard_rdo.html ./GO/templates/
cp /caminho/local/static/js/dashboard_rdo.js ./static/js/
# Atualizar setup/urls.py (ver instruções abaixo)
```

#### 3. Validar Instalação
```bash
# Verificar se Django está OK
python3 manage.py check

# Resultado esperado:
# System check identified no issues (0 silenced)
```

#### 4. Coletar Static Files (se em produção)
```bash
# Se usando produção, coletar static files
python3 manage.py collectstatic --noinput
```

#### 5. Testar Localmente
```bash
# Testar servidor local
python3 manage.py runserver

# Acessar em navegador:
# http://localhost:8000/dashboard/rdo/
```

#### 6. Reiniciar Aplicação (Produção)
```bash
# Se usando Gunicorn
sudo systemctl restart gunicorn

# Se usando uWSGI
sudo systemctl restart uwsgi

# Se usando supervisor
sudo supervisorctl restart gunicorn
```

---

## 🔧 Alterações Necessárias em `setup/urls.py`

**Localizar a seção de URLs do dashboard** (deve estar próximo ao final do arquivo):

```python
# Registrar endpoints da dashboard
urlpatterns += [
    path('api/dashboard/ordens_por_dia/', dashboard_views.ordens_por_dia, name='api_dashboard_ordens_por_dia'),
    path('api/dashboard/status_os/', dashboard_views.status_os, name='api_dashboard_status_os'),
    # ... outras rotas existentes ...
    
    # ADICIONAR ESTAS LINHAS ABAIXO:
    path('api/rdo-dashboard/hh_confinado_por_dia/', dashboard_views.rdo_soma_hh_confinado_por_dia, name='api_rdo_hh_confinado'),
    path('api/rdo-dashboard/hh_fora_confinado_por_dia/', dashboard_views.rdo_soma_hh_fora_confinado_por_dia, name='api_rdo_hh_fora_confinado'),
    path('api/rdo-dashboard/ensacamento_por_dia/', dashboard_views.rdo_ensacamento_por_dia, name='api_rdo_ensacamento'),
    path('api/rdo-dashboard/tambores_por_dia/', dashboard_views.rdo_tambores_por_dia, name='api_rdo_tambores'),
    path('api/rdo-dashboard/residuos_liquido_por_dia/', dashboard_views.rdo_residuos_liquido_por_dia, name='api_rdo_residuos_liquido'),
    path('api/rdo-dashboard/residuos_solido_por_dia/', dashboard_views.rdo_residuos_solido_por_dia, name='api_rdo_residuos_solido'),
    path('api/rdo-dashboard/liquido_por_supervisor/', dashboard_views.rdo_liquido_por_supervisor, name='api_rdo_liquido_supervisor'),
    path('api/rdo-dashboard/solido_por_supervisor/', dashboard_views.rdo_solido_por_supervisor, name='api_rdo_solido_supervisor'),
    path('api/rdo-dashboard/volume_por_tanque/', dashboard_views.rdo_volume_por_tanque, name='api_rdo_volume_tanque'),
    path('dashboard/rdo/', dashboard_views.rdo_dashboard_view, name='rdo_dashboard'),
]
```

---

## 🧪 Testes Pós-Instalação

### Teste 1: Validação Django
```bash
python3 manage.py check
# ✅ Esperado: System check identified no issues (0 silenced)
```

### Teste 2: Teste de URLs
```bash
# Acessar via curl ou navegador:
curl http://localhost:8000/dashboard/rdo/
# ✅ Esperado: HTML da página (autenticado)

# Sem autenticação:
curl http://localhost:8000/dashboard/rdo/ -i
# ✅ Esperado: 302 Redirect para /login/
```

### Teste 3: Teste de API
```bash
# Com cookies de autenticação:
curl http://localhost:8000/api/rdo-dashboard/hh_confinado_por_dia/?start=2025-11-01&end=2025-12-04
# ✅ Esperado: JSON com dados

# Exemplo de resposta:
{
  "success": true,
  "labels": ["2025-11-01", "2025-11-02", ...],
  "datasets": [{"label": "HH em espaço confinado", "data": [...]}]
}
```

### Teste 4: Verificar Filtros
1. Acessar `/dashboard/rdo/`
2. Mudar filtro de "Data Fim"
3. Clicar "🔄 Atualizar Gráficos"
4. ✅ Gráficos devem ser recarregados

### Teste 5: Verificar Dados
1. Verificar se existem registros RDO no banco:
```bash
python3 manage.py shell
>>> from GO.models import RDO
>>> RDO.objects.count()
# Deve retornar > 0
>>> RDO.objects.filter(data__isnull=False).exists()
# Deve retornar True
```

---

## 🔍 Troubleshooting Instalação

### Problema: "Template not found"
```
TemplateDoesNotExist: dashboard_rdo.html
```

**Solução:**
```bash
# Verificar se arquivo existe
ls -la GO/templates/dashboard_rdo.html

# Verificar se TEMPLATES está configurado
python3 manage.py shell
>>> from django.conf import settings
>>> print(settings.TEMPLATES)
```

### Problema: "ModuleNotFoundError: dashboard_views"
```
ModuleNotFoundError: No module named 'GO.dashboard_views'
```

**Solução:**
```bash
# Verificar se arquivo foi atualizado
ls -la GO/dashboard_views.py

# Restartar Django/Gunicorn para recarregar módulos
sudo systemctl restart gunicorn
```

### Problema: "404 Page not found"
```
Page not found (404): /dashboard/rdo/
```

**Solução:**
```bash
# Verificar se rota está registrada
python3 manage.py check

# Verificar urls.py
grep -n "rdo_dashboard_view" setup/urls.py
```

### Problema: Gráficos em branco
**Solução:**
```bash
# Verificar se há dados RDO
python3 manage.py shell
>>> from GO.models import RDO
>>> from django.utils import timezone
>>> from datetime import timedelta
>>> today = timezone.now().date()
>>> RDO.objects.filter(data__gte=today-timedelta(days=30), data__lte=today).count()
# Se retornar 0, criar dados de teste

# Ou verificar console do navegador (F12) para erros AJAX
```

### Problema: Cache não está funcionando
```bash
# Limpar cache se necessário
python3 manage.py shell
>>> from django.core.cache import cache
>>> cache.clear()

# Ou desabilitar cache temporariamente em dashboard_views.py
# Comente/remova as linhas com cache.set() e cache.get()
```

---

## 📊 Estrutura de Pastas Esperada

```
GESTAO_OPERACIONAL/
├── GO/
│   ├── templates/
│   │   ├── base.html
│   │   ├── home.html
│   │   ├── rdo.html
│   │   └── dashboard_rdo.html          ← NOVO
│   ├── dashboard_views.py               ← ATUALIZADO
│   ├── models.py
│   └── ...outros arquivos...
├── static/
│   ├── js/
│   │   ├── menu.js
│   │   ├── logout.js
│   │   └── dashboard_rdo.js             ← NOVO
│   ├── css/
│   └── img/
├── setup/
│   ├── urls.py                          ← ATUALIZADO
│   ├── settings.py
│   └── ...outros arquivos...
└── ...outros arquivos...
```

---

## 🚀 Deployment em Produção

### 1. Preparar servidor
```bash
cd /var/www/html/GESTAO_OPERACIONAL
git pull origin main  # ou seu branch
```

### 2. Atualizar código
```bash
# Copy files conforme instruções acima
```

### 3. Verificar integridade
```bash
python3 manage.py check
python3 manage.py test GO  # Se houver testes
```

### 4. Migrations (se necessário)
```bash
python3 manage.py migrate
```

### 5. Static Files
```bash
python3 manage.py collectstatic --noinput
```

### 6. Restart
```bash
sudo systemctl restart gunicorn
sudo systemctl restart nginx  # ou apache
```

### 7. Monitoramento
```bash
# Verificar logs
journalctl -u gunicorn -n 100

# Testar acesso
curl -I http://seu-dominio.com/dashboard/rdo/
# ✅ Esperado: HTTP 200 (com autenticação) ou 302 (sem autenticação)
```

---

## 📝 Notas Importantes

⚠️ **Backup**: Sempre fazer backup de `dashboard_views.py` e `setup/urls.py` antes de atualizar

⚠️ **Compatibilidade**: Dashboard requer Django 4.0+ (seus projeto já tem)

⚠️ **Dados**: Certifique-se de que existem RDOs com `data` preenchida

⚠️ **Permissions**: Usuário deve estar autenticado e ter permissão de acesso

⚠️ **Cache**: Tome cuidado ao limpar cache em produção (pode causar picos de carga)

---

## 📞 Suporte

Se encontrar problemas:

1. Verificar logs do Django: `journalctl -u gunicorn`
2. Abrir console do navegador: F12 → Console
3. Verificar network tab: F12 → Network
4. Testar API diretamente com curl
5. Validar dados no banco de dados

---

**Versão**: 1.0  
**Última atualização**: Dezembro 2025  
**Status**: ✅ Pronto para Deploy

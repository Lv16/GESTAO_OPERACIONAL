#!/bin/bash

# Script para testar otimizações de upload de fotos
# Autor: Sistema de Otimização
# Data: 15/01/2026

echo "================================================"
echo "  Teste de Otimizações de Upload de Fotos"
echo "================================================"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Diretório de fotos
FOTOS_DIR="/var/www/html/GESTAO_OPERACIONAL/fotos_rdo/rdos"
NGINX_CONF="/var/www/html/GESTAO_OPERACIONAL/deploy/nginx/gestao_operacional.conf"
SETTINGS_FILE="/var/www/html/GESTAO_OPERACIONAL/setup/settings.py"
JS_FILE="/var/www/html/GESTAO_OPERACIONAL/GO/static/js/rdo.js"

echo -e "${BLUE}[1/6] Verificando estrutura de diretórios...${NC}"
if [ -d "$FOTOS_DIR" ]; then
    echo -e "${GREEN}✓ Diretório de fotos existe: $FOTOS_DIR${NC}"
    
    # Estatísticas de fotos
    total_fotos=$(find "$FOTOS_DIR" -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \) | wc -l)
    echo -e "  Total de fotos: ${YELLOW}$total_fotos${NC}"
    
    if [ $total_fotos -gt 0 ]; then
        # Tamanho médio das fotos recentes (últimos 20 arquivos)
        echo -e "\n${BLUE}  Analisando fotos recentes...${NC}"
        avg_size=$(find "$FOTOS_DIR" -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \) -printf "%s\n" | sort -n | tail -20 | awk '{sum+=$1; count++} END {if(count>0) print int(sum/count/1024)}')
        
        if [ ! -z "$avg_size" ]; then
            echo -e "  Tamanho médio (últimas 20 fotos): ${YELLOW}${avg_size}KB${NC}"
            
            if [ $avg_size -lt 1000 ]; then
                echo -e "  ${GREEN}✓ Fotos estão otimizadas! (< 1MB)${NC}"
            elif [ $avg_size -lt 2000 ]; then
                echo -e "  ${YELLOW}⚠ Fotos poderiam ser mais otimizadas (1-2MB)${NC}"
            else
                echo -e "  ${RED}✗ Fotos muito grandes! (> 2MB)${NC}"
                echo -e "    ${YELLOW}Dica: Verifique se compressão está ativada${NC}"
            fi
        fi
    fi
else
    echo -e "${RED}✗ Diretório de fotos não encontrado!${NC}"
fi

echo ""
echo -e "${BLUE}[2/6] Verificando configuração Nginx...${NC}"
if [ -f "$NGINX_CONF" ]; then
    # Verificar client_max_body_size
    max_body=$(grep -oP 'client_max_body_size\s+\K[0-9]+M' "$NGINX_CONF" | head -1)
    if [ ! -z "$max_body" ]; then
        echo -e "${GREEN}✓ client_max_body_size: ${max_body}${NC}"
        
        size_num=$(echo $max_body | sed 's/M//')
        if [ $size_num -ge 50 ]; then
            echo -e "  ${GREEN}✓ Limite adequado para uploads (>= 50M)${NC}"
        else
            echo -e "  ${YELLOW}⚠ Limite baixo. Recomendado: 50M ou mais${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ client_max_body_size não encontrado${NC}"
    fi
    
    # Verificar timeouts
    body_timeout=$(grep -oP 'client_body_timeout\s+\K[0-9]+' "$NGINX_CONF" | head -1)
    if [ ! -z "$body_timeout" ]; then
        echo -e "${GREEN}✓ client_body_timeout: ${body_timeout}s${NC}"
        
        if [ $body_timeout -ge 300 ]; then
            echo -e "  ${GREEN}✓ Timeout adequado (>= 300s)${NC}"
        else
            echo -e "  ${YELLOW}⚠ Timeout pode ser insuficiente. Recomendado: 300s${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ Timeouts não configurados${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Arquivo de configuração Nginx não encontrado${NC}"
fi

echo ""
echo -e "${BLUE}[3/6] Verificando configuração Django...${NC}"
if [ -f "$SETTINGS_FILE" ]; then
    # Verificar DATA_UPLOAD_MAX_MEMORY_SIZE
    if grep -q "DATA_UPLOAD_MAX_MEMORY_SIZE" "$SETTINGS_FILE"; then
        echo -e "${GREEN}✓ DATA_UPLOAD_MAX_MEMORY_SIZE configurado${NC}"
    else
        echo -e "${YELLOW}⚠ DATA_UPLOAD_MAX_MEMORY_SIZE não encontrado${NC}"
    fi
    
    # Verificar FILE_UPLOAD_MAX_MEMORY_SIZE
    if grep -q "FILE_UPLOAD_MAX_MEMORY_SIZE" "$SETTINGS_FILE"; then
        echo -e "${GREEN}✓ FILE_UPLOAD_MAX_MEMORY_SIZE configurado${NC}"
    else
        echo -e "${YELLOW}⚠ FILE_UPLOAD_MAX_MEMORY_SIZE não encontrado${NC}"
    fi
else
    echo -e "${YELLOW}⚠ settings.py não encontrado${NC}"
fi

echo ""
echo -e "${BLUE}[4/6] Verificando JavaScript de compressão...${NC}"
if [ -f "$JS_FILE" ]; then
    # Verificar se função compressImage existe
    if grep -q "function compressImage" "$JS_FILE"; then
        echo -e "${GREEN}✓ Função compressImage encontrada${NC}"
        
        # Extrair configurações
        max_width=$(grep -oP 'MAX_WIDTH\s*=\s*\K[0-9]+' "$JS_FILE" | head -1)
        jpeg_quality=$(grep -oP 'JPEG_QUALITY\s*=\s*\K[0-9.]+' "$JS_FILE" | head -1)
        
        if [ ! -z "$max_width" ]; then
            echo -e "  MAX_WIDTH: ${YELLOW}${max_width}px${NC}"
        fi
        
        if [ ! -z "$jpeg_quality" ]; then
            quality_percent=$(echo "$jpeg_quality * 100" | bc)
            echo -e "  JPEG_QUALITY: ${YELLOW}${quality_percent}%${NC}"
        fi
    else
        echo -e "${RED}✗ Função de compressão não encontrada!${NC}"
        echo -e "  ${YELLOW}Execute o deploy das atualizações${NC}"
    fi
else
    echo -e "${RED}✗ Arquivo rdo.js não encontrado!${NC}"
fi

echo ""
echo -e "${BLUE}[5/6] Testando permissões de diretórios...${NC}"
if [ -w "$FOTOS_DIR" ]; then
    echo -e "${GREEN}✓ Diretório de fotos tem permissão de escrita${NC}"
    
    # Testar criação de arquivo
    test_file="$FOTOS_DIR/.write_test_$$"
    if touch "$test_file" 2>/dev/null; then
        echo -e "${GREEN}✓ Teste de escrita bem-sucedido${NC}"
        rm -f "$test_file"
    else
        echo -e "${RED}✗ Falha ao escrever no diretório${NC}"
    fi
else
    echo -e "${RED}✗ Diretório sem permissão de escrita${NC}"
    echo -e "  ${YELLOW}Execute: sudo chown -R www-data:www-data $FOTOS_DIR${NC}"
fi

echo ""
echo -e "${BLUE}[6/6] Verificando status dos serviços...${NC}"

# Nginx
if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓ Nginx está rodando${NC}"
    
    # Testar configuração
    if nginx -t 2>&1 | grep -q "successful"; then
        echo -e "${GREEN}✓ Configuração Nginx válida${NC}"
    else
        echo -e "${RED}✗ Configuração Nginx com erros${NC}"
        echo -e "  ${YELLOW}Execute: sudo nginx -t${NC}"
    fi
else
    echo -e "${RED}✗ Nginx não está rodando${NC}"
    echo -e "  ${YELLOW}Execute: sudo systemctl start nginx${NC}"
fi

# Gunicorn (se existir)
if systemctl list-units --full --all | grep -q "gunicorn"; then
    if systemctl is-active --quiet gunicorn; then
        echo -e "${GREEN}✓ Gunicorn está rodando${NC}"
    else
        echo -e "${YELLOW}⚠ Gunicorn não está rodando${NC}"
    fi
fi

echo ""
echo "================================================"
echo -e "${BLUE}Resumo e Recomendações:${NC}"
echo "================================================"

# Gerar recomendações
recommendations=0

if [ ! -z "$avg_size" ] && [ $avg_size -gt 1500 ]; then
    echo -e "${YELLOW}⚠ Fotos estão maiores que o esperado${NC}"
    echo -e "  → Verifique se compressão no cliente está ativa"
    echo -e "  → Limpe cache do browser: Ctrl+Shift+Delete"
    recommendations=$((recommendations + 1))
fi

if [ -z "$body_timeout" ] || [ $body_timeout -lt 300 ]; then
    echo -e "${YELLOW}⚠ Timeouts Nginx precisam ser aumentados${NC}"
    echo -e "  → Edite: $NGINX_CONF"
    echo -e "  → Adicione: client_body_timeout 300s;"
    echo -e "  → Execute: sudo systemctl restart nginx"
    recommendations=$((recommendations + 1))
fi

if ! grep -q "function compressImage" "$JS_FILE" 2>/dev/null; then
    echo -e "${RED}✗ Compressão JavaScript não está instalada${NC}"
    echo -e "  → Execute deploy das atualizações"
    echo -e "  → Limpe cache estático: python manage.py collectstatic"
    recommendations=$((recommendations + 1))
fi

if [ $recommendations -eq 0 ]; then
    echo -e "${GREEN}✓ Todas as otimizações estão configuradas corretamente!${NC}"
    echo ""
    echo -e "${BLUE}Próximos passos:${NC}"
    echo "1. Teste upload de fotos em um RDO"
    echo "2. Verifique console do browser (F12) para mensagens de compressão"
    echo "3. Monitore tamanho das novas fotos em: $FOTOS_DIR"
fi

echo ""
echo "================================================"
echo -e "${GREEN}Teste concluído!${NC}"
echo "================================================"

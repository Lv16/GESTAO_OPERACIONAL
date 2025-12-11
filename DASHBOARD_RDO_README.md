# Dashboard RDO - Guia de Uso

## 📊 Visão Geral

O novo **Dashboard RDO** é uma ferramenta completa para visualizar dados agregados de Relatórios Diários de Operação (RDO) com suporte a múltiplos filtros e 9 gráficos interativos.

## 🚀 Como Acessar

1. Acesse a URL: **`/dashboard/rdo/`**
2. Ou clique em "Dashboard RDO" no menu lateral da aplicação

## 📈 Gráficos Disponíveis

### 1. **HH em Espaço Confinado**
   - Mostra o total de horas-homem em espaço confinado por dia
   - Calculado a partir dos campos `entrada_confinado_1..6` e `saida_confinado_1..6`

### 2. **HH Fora de Espaço Confinado**
   - Total de horas-homem fora do espaço confinado por dia
   - Baseado no campo POB da Ordem de Serviço

### 3. **Ensacamento por Dia**
   - Quantidade total de ensacamentos realizados diariamente
   - Campo: `RDO.ensacamento`

### 4. **Tambores Gerados por Dia**
   - Número de tambores gerados por dia (calculado automaticamente como ceil(ensacamento / 10))
   - Campo: `RDO.tambores`

### 5. **M³ Resíduo Líquido Removido**
   - Volume de resíduo líquido processado por dia
   - Campo: `RDO.total_liquido`

### 6. **M³ Resíduo Sólido Removido**
   - Volume de resíduo sólido processado por dia
   - Campo: `RDO.total_solidos`

### 7. **M³ Líquido Removido por Supervisor**
   - Agregação total de resíduo líquido por supervisor (barra horizontal)
   - Permite comparar performance entre supervisores

### 8. **M³ Sólido Removido por Supervisor**
   - Agregação total de resíduo sólido por supervisor (barra horizontal)
   - Mostra distribuição de trabalho entre supervisores

### 9. **Volume Processado por Tanque**
   - Top 10 tanques com maior volume processado
   - Campo: `RDO.volume_tanque_exec`

## 🔍 Filtros Disponíveis

### Data
- **Data Início**: Filtrar RDOs a partir de uma data específica (padrão: 30 dias atrás)
- **Data Fim**: Filtrar RDOs até uma data específica (padrão: hoje)

### Operação
- **Supervisor**: Filtrar por supervisor (usuário) responsável
- **Cliente**: Filtrar por cliente da Ordem de Serviço
- **Unidade**: Filtrar por unidade/embarcação
- **Tanque**: Filtrar por nome/tipo de tanque

## 🎨 Funcionalidades

### Botões de Ação
- **🔄 Atualizar Gráficos**: Recarrega todos os gráficos com os filtros selecionados
- **↺ Limpar Filtros**: Reseta todos os filtros para os valores padrão (últimos 30 dias)

### Interatividade
- Todos os gráficos são responsivos e adaptativos
- Clique e arraste nos gráficos para zoom
- Passe o mouse sobre os dados para ver valores exatos
- Os gráficos são recarregados automaticamente ao mudar filtros

## 📊 Tipos de Gráficos

- **Gráficos de Série Temporal (Linha)**: HH Confinado, HH Fora Confinado
- **Gráficos de Barras Verticais**: Ensacamento, Tambores, Resíduos Líquido/Sólido, Volumes por Supervisor
- **Gráfico de Barras Horizontais**: Volume por Tanque (top 10)

## ⚙️ Endpoints da API

Todos os dados são obtidos via endpoints RESTful:

```
GET /api/rdo-dashboard/hh_confinado_por_dia/
GET /api/rdo-dashboard/hh_fora_confinado_por_dia/
GET /api/rdo-dashboard/ensacamento_por_dia/
GET /api/rdo-dashboard/tambores_por_dia/
GET /api/rdo-dashboard/residuos_liquido_por_dia/
GET /api/rdo-dashboard/residuos_solido_por_dia/
GET /api/rdo-dashboard/liquido_por_supervisor/
GET /api/rdo-dashboard/solido_por_supervisor/
GET /api/rdo-dashboard/volume_por_tanque/
```

### Parâmetros Query
Todos os endpoints suportam os seguintes parâmetros opcionais:

```
?start=YYYY-MM-DD&end=YYYY-MM-DD&supervisor=username&cliente=nome&unidade=nome&tanque=nome
```

## 🔐 Segurança

- O dashboard requer autenticação (login)
- Apenas usuários autenticados podem acessar
- Os dados são filtrados e agregados no servidor antes de serem enviados

## 📱 Responsividade

- O dashboard é totalmente responsivo
- Funciona em desktops, tablets e dispositivos móveis
- Grid adaptativo que se ajusta ao tamanho da tela

## 🐛 Troubleshooting

### Gráficos em branco
- Verifique se há dados RDO no período selecionado
- Revise os filtros aplicados
- Verifique se os campos `data` estão preenchidos nos RDOs

### Erro ao carregar dados
- Verifique a conexão de internet
- Verifique os logs do servidor Django
- Limpe o cache do navegador (Ctrl+Shift+Delete)

### Filtros não funcionam
- Certifique-se de clicar no botão "🔄 Atualizar Gráficos" após alterar filtros
- Verifique se os valores existem no banco de dados

## 📝 Notas Técnicas

- Cache de 60 segundos é aplicado nos endpoints para melhor performance
- Processamento de dados é feito no servidor (seguro e eficiente)
- Gráficos usam Chart.js 3.9.1 (biblioteca open-source)

## 🎯 Próximas Melhorias Sugeridas

1. Exportar dados para PDF/Excel
2. Agendamento de relatórios automáticos
3. Alertas de anomalias nos dados
4. Comparação entre períodos
5. Mais gráficos de análise (comparativa, tendências, etc.)

---

**Última atualização**: Dezembro 2025

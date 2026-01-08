import os
import sys
import django
from faker import Faker
from decimal import Decimal
from datetime import date, timedelta
import random

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings_dev')
django.setup()

from GO.models import Cliente, Unidade, OrdemServico, Pessoa, Funcao, RDO, RDOMembroEquipe, RDOAtividade, Equipamentos, Modelo
from django.contrib.auth import get_user_model

User = get_user_model()

fake = Faker('pt_BR')  # Portuguese for Brazilian names/companies

def clear_database():
    print("Clearing database...")
    print("  Deletando RDOAtividade...")
    RDOAtividade.objects.all().delete()
    print("  Deletando RDOMembroEquipe...")
    RDOMembroEquipe.objects.all().delete()
    print("  Deletando RDO...")
    RDO.objects.all().delete()
    print("  Deletando OrdemServico...")
    OrdemServico.objects.all().delete()
    print("  Deletando Pessoa...")
    Pessoa.objects.all().delete()
    print("  Deletando Funcao...")
    Funcao.objects.all().delete()
    print("  Deletando EquipamentoFoto...")
    from GO.models import EquipamentoFoto
    EquipamentoFoto.objects.all().delete()
    print("  Deletando Equipamentos...")
    Equipamentos.objects.all().delete()
    print("  Deletando Modelo...")
    Modelo.objects.all().delete()
    print("  Deletando Unidade...")
    Unidade.objects.all().delete()
    print("  Deletando Cliente...")
    Cliente.objects.all().delete()
    print("✓ Banco de dados limpo com sucesso!")


def create_fake_data():
    print("\n📊 Criando dados fictícios em grande volume...\n")

    # ========== CRIAR USUÁRIOS SUPERVISORES ==========
    print("➤ Criando Usuários Supervisores...")
    supervisores = []
    nomes_supervisores = [
        ('João Silva', 'joao.silva@empresa.com'),
        ('Maria Santos', 'maria.santos@empresa.com'),
        ('Carlos Oliveira', 'carlos.oliveira@empresa.com'),
        ('Ana Costa', 'ana.costa@empresa.com'),
        ('Pedro Almeida', 'pedro.almeida@empresa.com')
    ]
    
    for nome, email in nomes_supervisores:
        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                password='senha123',
                first_name=nome.split()[0],
                last_name=' '.join(nome.split()[1:]),
                is_staff=True,
                is_active=True
            )
            supervisores.append(user)
        except Exception:
            # Se já existe, buscar
            try:
                user = User.objects.get(username=email)
                supervisores.append(user)
            except:
                pass
    
    print(f"✓ {len(supervisores)} supervisores criados/encontrados")

    # ========== CRIAR CLIENTES ==========
    print("➤ Criando 15 Clientes...")
    clientes = []
    nomes_clientes = [
        "Petrobras", "Shell Brasil", "Chevron", "TechnipFMC", "SLB",
        "Baker Hughes", "Halliburton", "ENSCO", "Weatherford", "NOW",
        "National Oilwell Varco", "Nabors", "Transocean", "Seadrill", "DHI"
    ]
    for nome in nomes_clientes:
        cliente = Cliente.objects.create(nome=nome)
        clientes.append(cliente)
    print(f"✓ {len(clientes)} clientes criados")

    # ========== CRIAR UNIDADES ==========
    print("➤ Criando 10 Unidades/Navios...")
    unidades = []
    nomes_unidades = [
        "Navio A", "Navio B", "Navio C", "Plataforma 1", "Plataforma 2",
        "Estaleiro Rio", "Estaleiro SP", "Terminal Santos", "Terminal Itaguaí", "Offshore AC"
    ]
    for nome in nomes_unidades:
        unidade = Unidade.objects.create(nome=nome)
        unidades.append(unidade)
    print(f"✓ {len(unidades)} unidades criadas")

    # ========== CRIAR FUNÇÕES ==========
    print("➤ Criando Funções...")
    funcoes = []
    funcao_names = ['SUPERVISOR', 'ELETRICISTA', 'TÉCNICO DE SEGURANÇA', 'AJUDANTE', 'MECÂNICO']
    for name in funcao_names:
        funcao = Funcao.objects.create(nome=name)
        funcoes.append(funcao)
    print(f"✓ {len(funcoes)} funções criadas")

    # ========== CRIAR PESSOAS ==========
    print("➤ Criando 50 Pessoas/Colaboradores...")
    pessoas = []
    for i in range(50):
        pessoa = Pessoa.objects.create(
            nome=fake.name(),
            funcao=random.choice(funcoes).nome
        )
        pessoas.append(pessoa)
    print(f"✓ {len(pessoas)} pessoas criadas")

    # ========== CRIAR ORDENS DE SERVIÇO ==========
    print("➤ Criando 30 Ordens de Serviço...")
    ordens = []
    servicos = ['Limpeza', 'Inspeção', 'Reparação', 'Manutenção', 'Teste de Pressão']
    metodos = ['Manual', 'Mecanizada', 'Jato de Água', 'Químico']
    
    # Datas distribuídas ao longo do ano
    data_base = date(2024, 1, 1)
    
    for i in range(30):
        # Distribuir datas ao longo de 12 meses
        dias_offset = (i * 12) % 365
        data_inicio = data_base + timedelta(days=dias_offset)
        dias_duracao = random.randint(5, 30)
        data_fim = data_inicio + timedelta(days=dias_duracao)
        
        numero_os_unico = 10000 + i  # Garante números únicos
        
        ordem = OrdemServico.objects.create(
            numero_os=numero_os_unico,
            data_inicio=data_inicio,
            data_fim=data_fim,
            dias_de_operacao=dias_duracao,
            servico=random.choice(servicos),
            metodo=random.choice(metodos),
            pob=random.randint(2, 15),
            volume_tanque=Decimal(random.uniform(500, 15000)),
            Cliente=random.choice(clientes),
            Unidade=random.choice(unidades),
            tipo_operacao=random.choice(['ONSHORE', 'OFFSHORE', 'SPOT']),
            solicitante=fake.name(),
            coordenador=fake.name(),
            supervisor=random.choice(supervisores) if supervisores else None,
            status_operacao=random.choice(['Planejada', 'Em Andamento', 'Concluída']),
            status_comercial=random.choice(['Orçado', 'Contratado', 'Faturado']),
        )
        ordens.append(ordem)
    print(f"✓ {len(ordens)} ordens de serviço criadas")

    # ========== CRIAR RDOs ==========
    print("➤ Criando RDOs espaçados para melhor visualização no dashboard...")
    rdos = []
    turnos = ['Diurno', 'Noturno']
    tipos_tanque = ['Salão', 'Compartimento']
    
    # Criar RDOs espaçados ao longo de 2024 (2-3 por semana para visualização limpa)
    rdo_counter = 0
    start_date = date(2024, 1, 1)
    end_date = date(2024, 12, 31)
    current_date = start_date
    
    while current_date <= end_date:
        # Criar 2-3 RDOs por semana
        rdos_nesta_semana = random.randint(2, 3)
        
        for _ in range(rdos_nesta_semana):
            # Selecionar uma ordem aleatória
            ordem = random.choice(ordens)
            
            # Avançar 1-3 dias
            dias_avancar = random.randint(1, 3)
            rdo_data = current_date + timedelta(days=dias_avancar)
            
            if rdo_data > end_date:
                break
            if rdo_data > end_date:
                break
            
            # Gerar horários de entrada/saída para espaço confinado (1 a 3 pares)
            num_entradas_confinado = random.randint(1, 3)
            entrada_saida_data = {}
            
            for ec_idx in range(1, num_entradas_confinado + 1):
                hora_entrada = random.randint(7, 14)
                minuto_entrada = random.randint(0, 59)
                hora_saida = hora_entrada + random.randint(2, 6)  # 2-6 horas depois
                minuto_saida = random.randint(0, 59)
                
                from datetime import time as dt_time
                entrada_saida_data[f'entrada_confinado_{ec_idx}'] = dt_time(hora_entrada, minuto_entrada)
                entrada_saida_data[f'saida_confinado_{ec_idx}'] = dt_time(min(hora_saida, 22), minuto_saida)
            
            rdo = RDO.objects.create(
                ordem_servico=ordem,
                data=rdo_data,
                data_inicio=rdo_data,
                turno=random.choice(turnos),
                contrato_po=f"PO{random.randint(1000, 9999)}",
                exist_pt=random.choice([True, False]),
                tipo_tanque=random.choice(tipos_tanque),
                nome_tanque=f"Tanque {random.randint(1, 100)}",
                volume_tanque_exec=Decimal(random.uniform(200, 8000)),
                servico_exec=random.choice(servicos),
                metodo_exec=random.choice(metodos),
                gavetas=random.randint(0, 6),
                patamares=random.randint(0, 4),
                confinado=random.choice([True, False]),
                # Horários de entrada/saída em espaço confinado
                **entrada_saida_data,
                # Dados operacionais para o dashboard - valores mais variados
                ensacamento=random.randint(100, 800),
                tambores=random.randint(10, 50),
                total_liquido=random.randint(500, 8000),
                total_solidos=random.randint(200, 2000),
                total_residuos=random.randint(700, 10000),
            )
            rdos.append(rdo)
            rdo_counter += 1
        
        # Avançar para próxima semana
        current_date += timedelta(days=7)
    
    print(f"✓ {rdo_counter} RDOs criadas")

    # ========== CRIAR MEMBROS DA EQUIPE ==========
    print("➤ Adicionando Membros da Equipe às RDOs...")
    membros_batch = []
    for rdo in rdos:
        num_membros = random.randint(3, 8)
        selected_pessoas = random.sample(pessoas, min(num_membros, len(pessoas)))
        
        for i, pessoa in enumerate(selected_pessoas):
            membros_batch.append(RDOMembroEquipe(
                rdo=rdo,
                pessoa=pessoa,
                nome=pessoa.nome,
                funcao=pessoa.funcao,
                em_servico=random.choice([True, True, False]),  # 2/3 chance of True
                ordem=i
            ))
    
    RDOMembroEquipe.objects.bulk_create(membros_batch, batch_size=500)
    print(f"✓ {len(membros_batch)} membros de equipe associados")

    # ========== CRIAR ATIVIDADES ==========
    print("➤ Adicionando Atividades às RDOs...")
    atividades_opcoes = [
        'Preparo do Tanque',
        'Limpeza com Jato',
        'Inspeção Interna',
        'Teste de Estanqueidade',
        'Reparação de Componentes',
        'Revestimento',
        'Secagem',
        'Testes Finais',
        'Documentação'
    ]
    
    atividades_batch = []
    for rdo in rdos:
        num_atividades = random.randint(4, 10)
        
        for i in range(num_atividades):
            hora_inicio_h = random.randint(6, 18)
            hora_inicio_m = random.randint(0, 59)
            hora_fim_h = random.randint(hora_inicio_h + 1, 22)
            hora_fim_m = random.randint(0, 59)
            
            hora_inicio = f"{hora_inicio_h:02d}:{hora_inicio_m:02d}"
            hora_fim = f"{hora_fim_h:02d}:{hora_fim_m:02d}"
            
            atividades_batch.append(RDOAtividade(
                rdo=rdo,
                ordem=i,
                atividade=random.choice(atividades_opcoes),
                inicio=hora_inicio,
                fim=hora_fim,
                comentario_pt=fake.sentence()
            ))
    
    RDOAtividade.objects.bulk_create(atividades_batch, batch_size=500)
    print(f"✓ {len(atividades_batch)} atividades criadas")

    # ========== CRIAR MODELOS DE EQUIPAMENTO ==========
    print("➤ Criando Modelos de Equipamento...")
    modelos = []
    modelo_names = [
        'Bomba Centrífuga XYZ-100',
        'Compressor de Ar CAC-500',
        'Gerador Diesel GEN-250',
        'Carro de Limpeza CL-1000',
        'Escafandro Equipado ES-200',
        'Cilindro de Ar Comprimido AC-80',
        'Mangote de Alta Pressão MAP-50',
        'Unidade de Filtração UF-300'
    ]
    
    for name in modelo_names:
        modelo = Modelo.objects.create(
            nome=name,
            fabricante=fake.company(),
            descricao=fake.sentence()
        )
        modelos.append(modelo)
    print(f"✓ {len(modelos)} modelos de equipamento criados")

    # ========== CRIAR EQUIPAMENTOS ==========
    print("➤ Criando 50 Equipamentos...")
    equipamentos_criados = 0
    for i in range(50):
        numero_serie_unico = f"SER-{i:05d}"  # Garante unicidade
        numero_tag_unico = f"TAG-{i:05d}"
        
        equipamento = Equipamentos.objects.create(
            modelo=random.choice(modelos),
            numero_serie=numero_serie_unico,
            numero_tag=numero_tag_unico,
            cliente=random.choice(clientes).nome,
            embarcacao=random.choice(unidades).nome,
            numero_os=str(random.choice(ordens).numero_os)
        )
        equipamentos_criados += 1
    
    print(f"✓ {equipamentos_criados} equipamentos criados")

    # ========== RESUMO FINAL ==========
    print("\n" + "="*60)
    print("✨ DADOS FICTÍCIOS CARREGADOS COM SUCESSO! ✨")
    print("="*60)
    print(f"📊 Resumo:")
    print(f"  • Supervisores: {len(supervisores)}")
    print(f"  • Clientes: {len(clientes)}")
    print(f"  • Unidades: {len(unidades)}")
    print(f"  • Pessoas: {len(pessoas)}")
    print(f"  • Funções: {len(funcoes)}")
    print(f"  • Ordens de Serviço: {len(ordens)}")
    print(f"  • RDOs: {rdo_counter}")
    print(f"  • Atividades: {len(atividades_batch)}")
    print(f"  • Equipamentos: {equipamentos_criados}")
    print("="*60)
    print("\n🚀 Agora você tem muitos dados para visualizar no dashboard!")
    print("   Acesse: http://localhost:8001/dashboard/rdo/\n")

if __name__ == '__main__':
    clear_database()
    create_fake_data()
from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.test.utils import override_settings
from django.urls import reverse

from GO.models import Cliente, OrdemServico, Unidade


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class CoordinatorFilterTests(TestCase):
    """Test coordinator filter on home page"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='coordinator_filter_test',
            password='password123',
        )
        self.client = Client()
        self.client.force_login(self.user)
        
        self.cliente = Cliente.objects.create(nome='Test Cliente')
        self.unidade = Unidade.objects.create(nome='Test Unidade')
        
        # Get first two distinct coordinators
        self.coordenador_1 = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.coordenadores = [c[0] for c in OrdemServico.COORDENADORES if c[0]]
        self.coordenador_2 = self.coordenadores[1] if len(self.coordenadores) > 1 else self.coordenador_1
    
    def _create_os(self, numero_os, coordenador):
        """Helper to create an OS with given coordinator"""
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 3, 26),
            data_fim=None,
            dias_de_operacao=0,
            servico='COLETA DE AR',
            servicos='COLETA DE AR',
            metodo='Manual',
            pob=1,
            tanque='',
            tanques=None,
            volume_tanque=Decimal('0.00'),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao='Onshore',
            solicitante='Test Solicitante',
            coordenador=coordenador,
            status_operacao='Programada',
            status_geral='Programada',
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )
    
    def test_home_filters_by_coordinator_single_value(self):
        """Test filtering by a single coordinator"""
        os_coord1_a = self._create_os(60001, self.coordenador_1)
        os_coord1_b = self._create_os(60002, self.coordenador_1)
        os_coord2 = self._create_os(60003, self.coordenador_2)
        
        # Filter by coordinator 1
        response = self.client.get(reverse('home'), {'coordenador': self.coordenador_1})
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        servicos = list(response.context['servicos'].object_list)
        self.assertEqual(len(servicos), 2)
        self.assertIn(os_coord1_a.pk, [os.pk for os in servicos])
        self.assertIn(os_coord1_b.pk, [os.pk for os in servicos])
        self.assertNotIn(os_coord2.pk, [os.pk for os in servicos])
        
        # Verify active filter chip shows
        self.assertEqual(
            response.context['filtros_ativos'].get('Coordenador'),
            self.coordenador_1,
        )
    
    def test_home_coordinator_filter_in_template_choices(self):
        """Test that coordinator filter appears in template"""
        response = self.client.get(reverse('home'))
        
        self.assertEqual(response.status_code, 200)
        # Check that the form has coordenador field with choices
        form = response.context['form']
        self.assertIn('coordenador', form.fields)
        choices = form.fields['coordenador'].choices
        
        # Should have multiple coordinator options
        self.assertGreater(len(choices), 1)
        
        # Verify some expected coordinators are there
        choice_values = [c[0] for c in choices]
        self.assertIn(self.coordenador_1, choice_values)
        self.assertIn(self.coordenador_2, choice_values)
    
    def test_lista_servicos_filters_by_coordinator(self):
        """Test coordinator filter on lista_servicos view"""
        os_coord1 = self._create_os(61001, self.coordenador_1)
        os_coord2 = self._create_os(61002, self.coordenador_2)
        
        response = self.client.get(reverse('lista_servicos'), {'coordenador': self.coordenador_1})
        
        self.assertEqual(response.status_code, 200)
        servicos = list(response.context['servicos'].object_list)
        
        # Should only get coordinator 1's OS
        self.assertEqual(len(servicos), 1)
        self.assertEqual(servicos[0].pk, os_coord1.pk)

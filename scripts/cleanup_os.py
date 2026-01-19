import os
import sys
from django import setup

proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
setup()
from GO.models import OrdemServico
from django.db import connection

print('count before:', OrdemServico.objects.count())
OrdemServico.objects.all().delete()
print('deleted all OrdemServico')
with connection.cursor() as cursor:
    try:
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='GO_ordemservico'")
        print('sqlite_sequence entry deleted')
    except Exception as e:
        print('could not delete sqlite_sequence entry:', e)
    try:
        cursor.execute('VACUUM')
        print('VACUUM executed')
    except Exception as e:
        print('could not run VACUUM:', e)

print('count after:', OrdemServico.objects.count())
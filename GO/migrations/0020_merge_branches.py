"""Merge migration to resolve conflicting branches.

This migration merges the branch that adds the 'tanques' field
with the branch that introduced several other changes (0019).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0012_add_tanques_field'),
        ('GO', '0019_rdo_vazao_bombeio'),
    ]

    operations = [
    ]

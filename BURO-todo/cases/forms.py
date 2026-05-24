from django import forms

from cases.models import AssignmentCriteriaConfig


class AssignmentCriteriaForm(forms.ModelForm):
    class Meta:
        model = AssignmentCriteriaConfig
        fields = [
            'max_cases_per_professor',
            'prioritize_same_room',
            'balance_workload',
            'active',
        ]
        labels = {
            'max_cases_per_professor': 'Máximo de casos por profesor',
            'prioritize_same_room': 'Priorizar misma sala',
            'balance_workload': 'Equilibrar carga de trabajo',
            'active': 'Configuración activa',
        }
        help_texts = {
            'max_cases_per_professor': 'Número mínimo de casos que puede tener asignado un profesor.',
            'prioritize_same_room': 'Si está activado, el sistema prioriza asignar casos a profesores de la misma sala.',
            'balance_workload': 'Si está activado, el sistema intenta equilibrar la carga de trabajo entre profesores.',
            'active': 'Solo una configuración puede estar activa al mismo tiempo.',
        }
        widgets = {
            'max_cases_per_professor': forms.NumberInput(attrs={'min': 1, 'class': 'w-full rounded-2xl border border-slate-700 bg-slate-800 px-4 py-3 text-white'}),
            'prioritize_same_room': forms.CheckboxInput(attrs={'class': 'h-5 w-5 rounded text-yellow-400'}),
            'balance_workload': forms.CheckboxInput(attrs={'class': 'h-5 w-5 rounded text-yellow-400'}),
            'active': forms.CheckboxInput(attrs={'class': 'h-5 w-5 rounded text-yellow-400'}),
        }

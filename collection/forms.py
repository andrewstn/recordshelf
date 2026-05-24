from django import forms
from .models import CollectionItem

class CollectionItemForm(forms.ModelForm):
    class Meta:
        model = CollectionItem
        fields = ['variant_description', 'rating']
        widgets = {
            'variant_description': forms.TextInput(attrs={
                'class': 'w-full bg-zinc-900 border border-zinc-700 rounded-md p-4 text-white focus:border-brand focus:ring-1 focus:ring-brand outline-none transition',
                'placeholder': 'e.g. 180g Translucent Red, 10th Anniversary'
            }),
            'rating': forms.NumberInput(attrs={
                'class': 'w-full bg-zinc-900 border border-zinc-700 rounded-md p-4 text-white focus:border-brand focus:ring-1 focus:ring-brand outline-none transition',
                'min': 1,
                'max': 5,
                'placeholder': '1-5 Stars'
            }),
        }
        
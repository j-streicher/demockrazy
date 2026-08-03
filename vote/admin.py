from django.contrib import admin

# Register your models here.
from .models import Choice, Poll, Token

admin.site.register(Poll)
admin.site.register(Choice)
admin.site.register(Token)

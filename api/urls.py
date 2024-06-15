from django.urls import path
from .views import get_profile, hello_world

urlpatterns = [
    path('get_profile/', get_profile, name='get_profile'),
    path('hello_world/', hello_world, name='hello_world')
]

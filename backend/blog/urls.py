from django.urls import path

from .views import BlogDetailView, BlogListView

app_name = 'blog'

urlpatterns = [
    path('', BlogListView.as_view(), name='list'),
    path('<slug:slug>/', BlogDetailView.as_view(), name='detail'),
]

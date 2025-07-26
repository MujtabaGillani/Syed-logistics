"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('coreFE.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    # Serve static files from root paths for Frontend files
    urlpatterns += static('/css/', document_root=settings.STATICFILES_DIRS[0] / 'css')
    urlpatterns += static('/js/', document_root=settings.STATICFILES_DIRS[0] / 'js')
    urlpatterns += static('/img/', document_root=settings.STATICFILES_DIRS[0] / 'img')
    urlpatterns += static('/lib/', document_root=settings.STATICFILES_DIRS[0] / 'lib')

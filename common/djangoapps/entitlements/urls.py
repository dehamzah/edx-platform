from django.conf.urls import url, patterns, include
from rest_framework.routers import DefaultRouter

from .views import EntitlementViewSet

router = DefaultRouter()
router.register(r'entitlements', EntitlementViewSet, base_name='entitlements')

urlpatterns = patterns(
    'entitlements.views',
    url(r'', include(router.urls)),
)

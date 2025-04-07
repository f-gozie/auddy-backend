from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from auddy_backend.users.api.views import UserViewSet
from auddy_backend.extraction.api.views import ExtractionViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("extract", ExtractionViewSet, basename="extract")


app_name = "api"
urlpatterns = router.urls

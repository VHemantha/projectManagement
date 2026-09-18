from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import FilterViewSet, quick_search

router = SimpleRouter()
router.register("filters", FilterViewSet, basename="filter")

urlpatterns = [
    path("quick/", quick_search, name="quick-search"),
    path("", include(router.urls)),
]

from rest_framework import generics
from rest_framework.permissions import AllowAny

from apps.catalog.search import available_apartments, search_catalog
from apps.catalog.serializers import ApartmentSerializer


class ApartmentListAPIView(generics.ListAPIView):
    serializer_class = ApartmentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return search_catalog(self.request.query_params)


class ApartmentDetailAPIView(generics.RetrieveAPIView):
    serializer_class = ApartmentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return available_apartments()

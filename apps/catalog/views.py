from decimal import Decimal, InvalidOperation

from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny

from apps.catalog.models import Apartment
from apps.catalog.serializers import ApartmentSerializer


class ApartmentListAPIView(generics.ListAPIView):
    serializer_class = ApartmentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = (
            Apartment.objects
            .filter(
                source_type=Apartment.SourceType.FLAT,
                source_status=Apartment.SourceStatus.AVAILABLE,
                price_rub__gt=0,
            )
            .select_related(
                "floor",
                "floor__section",
                "floor__section__building",
                "floor__section__building__stage",
                "floor__section__building__stage__complex",
            )
        )

        params = self.request.query_params

        complex_id = self._get_int_param(
            params,
            "complex_id",
            min_value=1,
        )

        if complex_id is not None:
            queryset = queryset.filter(
                floor__section__building__stage__complex_id=complex_id
            )

        # Количество комнат
        rooms = self._get_int_param(params, "rooms", min_value=0)
        if rooms is not None:
            queryset = queryset.filter(rooms=rooms)

        # Этаж. Отрицательное значение допускается, например -1.
        floor = self._get_int_param(params, "floor")
        if floor is not None:
            queryset = queryset.filter(floor__number=floor)

        # Диапазон цены
        min_price = self._get_decimal_param(params, "min_price")
        max_price = self._get_decimal_param(params, "max_price")

        if min_price is not None and max_price is not None:
            if min_price > max_price:
                raise ValidationError({
                    "price": "min_price не может быть больше max_price."
                })

        if min_price is not None:
            queryset = queryset.filter(price_rub__gte=min_price)

        if max_price is not None:
            queryset = queryset.filter(price_rub__lte=max_price)

        # Диапазон площади
        min_area = self._get_decimal_param(params, "min_area")
        max_area = self._get_decimal_param(params, "max_area")

        if min_area is not None and max_area is not None:
            if min_area > max_area:
                raise ValidationError({
                    "area": "min_area не может быть больше max_area."
                })

        if min_area is not None:
            queryset = queryset.filter(area_m2__gte=min_area)

        if max_area is not None:
            queryset = queryset.filter(area_m2__lte=max_area)

        return queryset.order_by("price_rub")

    @staticmethod
    def _get_int_param(params, name, min_value=None):
        value = params.get(name)

        if value is None or value == "":
            return None

        try:
            result = int(value)
        except (TypeError, ValueError):
            raise ValidationError({
                name: "Укажите целое число."
            })

        if min_value is not None and result < min_value:
            raise ValidationError({
                name: f"Значение должно быть не меньше {min_value}."
            })

        return result

    @staticmethod
    def _get_decimal_param(params, name):
        value = params.get(name)

        if value is None or value == "":
            return None

        try:
            result = Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError({
                name: "Укажите корректное число."
            })

        if not result.is_finite() or result < 0:
            raise ValidationError({
                name: "Значение должно быть конечным неотрицательным числом."
            })

        return result


class ApartmentDetailAPIView(generics.RetrieveAPIView):
    serializer_class = ApartmentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return (
            Apartment.objects
            .filter(
                source_type=Apartment.SourceType.FLAT,
                source_status=Apartment.SourceStatus.AVAILABLE,
                price_rub__gt=0,
            )
            .select_related(
                "floor",
                "floor__section",
                "floor__section__building",
                "floor__section__building__stage",
                "floor__section__building__stage__complex",
            )
        )
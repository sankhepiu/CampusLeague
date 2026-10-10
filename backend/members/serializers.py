from rest_framework import serializers

from shop.payments import OUTCOMES, SUCCESS

from .models import Membership, MembershipPlan


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipPlan
        fields = ['id', 'name', 'price', 'duration_months', 'ticket_discount_pct', 'merch_discount_pct']
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'plan', 'status', 'start_date', 'end_date']
        read_only_fields = fields


class MembershipPurchaseSerializer(serializers.Serializer):
    # The client names a plan and nothing else about the money. A price,
    # total or user id in the body is ignored.
    #
    # Inactive plans are left out of the queryset, so they are reported the
    # same way as a plan that does not exist.
    plan = serializers.PrimaryKeyRelatedField(queryset=MembershipPlan.objects.filter(active=True))
    # Plan: "The mock gateway accepts a test card flag so the frontend can
    # demo both success and failure."
    # ASSUMPTION: the flag is this field, defaulting to success.
    test_outcome = serializers.ChoiceField(choices=OUTCOMES, default=SUCCESS)

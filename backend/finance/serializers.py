from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from common.validation import MAX_AMOUNT

from .models import ExpenseRequest, LedgerEntry, LedgerLine

# Plan: "Accept images or PDFs for receipts, with a size limit and type check."
MAX_RECEIPT_BYTES = 5 * 1024 * 1024
# extension -> the bytes a real file of that type starts with. Checking the
# content, not just the name, stops a renamed file getting through.
RECEIPT_SIGNATURES = {
    'pdf': [b'%PDF-'],
    'png': [b'\x89PNG\r\n\x1a\n'],
    'jpg': [b'\xff\xd8\xff'],
    'jpeg': [b'\xff\xd8\xff'],
}
# extension -> the Content-Type the upload must declare. Three checks in
# all (name, declared type, actual bytes); a file has to pass every one.
RECEIPT_CONTENT_TYPES = {
    'pdf': {'application/pdf'},
    'png': {'image/png'},
    'jpg': {'image/jpeg'},
    'jpeg': {'image/jpeg'},
}


def error(message, code):
    return [ErrorDetail(message, code=code)]


class ExpenseSerializer(serializers.ModelSerializer):
    requester = serializers.SerializerMethodField()
    receipt_url = serializers.SerializerMethodField()
    approval = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseRequest
        fields = [
            'id', 'requester', 'amount', 'category', 'event', 'fundraiser', 'description',
            'receipt_url', 'status', 'created_at', 'approval',
        ]
        read_only_fields = fields

    def get_requester(self, expense):
        return {'id': expense.requester_id, 'name': expense.requester.name}

    def get_receipt_url(self, expense):
        # Relative (/media/receipts/...), the same form the trace endpoint
        # returns, so the frontend reaches every receipt through its own
        # /media proxy regardless of which host the API is on.
        return expense.receipt_file.url

    def get_approval(self, expense):
        approval = getattr(expense, 'approval', None)
        if approval is None:
            return None
        return {
            'decision': approval.decision, 'reason': approval.reason, 'decided_at': approval.decided_at,
            'approver': {'id': approval.approver_id, 'name': approval.approver.name},
        }


class ExpenseSubmitSerializer(serializers.ModelSerializer):
    amount = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT)
    description = serializers.CharField(max_length=500, min_length=3)

    class Meta:
        model = ExpenseRequest
        # No requester and no status: the requester is the logged-in user and
        # every request starts as "submitted".
        fields = ['amount', 'category', 'event', 'fundraiser', 'description', 'receipt_file']

    def validate_receipt_file(self, upload):
        extension = upload.name.rsplit('.', 1)[-1].lower() if '.' in upload.name else ''
        if extension not in RECEIPT_SIGNATURES:
            raise serializers.ValidationError(
                ErrorDetail('Upload the receipt as a JPG, PNG or PDF.', code='unsupported_file_type')
            )
        if upload.size > MAX_RECEIPT_BYTES:
            raise serializers.ValidationError(ErrorDetail('The receipt must be 5 MB or smaller.', code='file_too_large'))
        if (upload.content_type or '').split(';')[0].strip().lower() not in RECEIPT_CONTENT_TYPES[extension]:
            raise serializers.ValidationError(ErrorDetail(
                f'A .{extension} file must be sent as {sorted(RECEIPT_CONTENT_TYPES[extension])[0]}.',
                code='content_type_mismatch',
            ))
        start = upload.read(8)
        upload.seek(0)
        if not any(start.startswith(signature) for signature in RECEIPT_SIGNATURES[extension]):
            raise serializers.ValidationError(
                ErrorDetail(f'This file is not a valid {extension.upper()}.', code='file_content_mismatch')
            )
        return upload

    def validate(self, attrs):
        category, event, fundraiser = attrs['category'], attrs.get('event'), attrs.get('fundraiser')
        if category == 'event' and (event is None or fundraiser is not None):
            raise serializers.ValidationError({'event': error('An event expense needs an event (and no fundraiser).', 'event_required')})
        if category == 'fundraiser' and (fundraiser is None or event is not None):
            raise serializers.ValidationError({'fundraiser': error('A fundraiser expense needs a fundraiser (and no event).', 'fundraiser_required')})
        if category == 'general' and (event is not None or fundraiser is not None):
            raise serializers.ValidationError({'category': error('A general expense cannot name an event or fundraiser.', 'tag_not_allowed')})
        return attrs


class DecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')


class RejectionSerializer(serializers.Serializer):
    # ASSUMPTION: a rejection must say why; an approval need not.
    reason = serializers.CharField(max_length=500)


class LedgerLineSerializer(serializers.ModelSerializer):
    account = serializers.SerializerMethodField()

    class Meta:
        model = LedgerLine
        fields = ['id', 'account', 'debit', 'credit']
        read_only_fields = fields

    def get_account(self, line):
        return {'code': line.account.code, 'name': line.account.name, 'type': line.account.type}


class LedgerEntrySerializer(serializers.ModelSerializer):
    lines = LedgerLineSerializer(many=True, read_only=True)

    class Meta:
        model = LedgerEntry
        fields = ['id', 'posted_at', 'description', 'source_type', 'source_id', 'kind', 'event', 'reverses', 'lines']
        read_only_fields = fields

"""Payment validation helpers (string sets for API / service checks)."""

from __future__ import annotations

from domains.payments.domain.enums import PaymentMode

PAYMENT_MODES = frozenset(m.value for m in PaymentMode)

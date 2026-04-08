from domains.audit.infrastructure import models as audit_models  # noqa: F401
from domains.bookings.infrastructure import models as booking_models  # noqa: F401
from domains.catalog.infrastructure import models as catalog_models  # noqa: F401
# from domains.customers.infrastructure import models as customer_models  # noqa: F401
from domains.franchises.infrastructure import models as franchise_models  # noqa: F401
from domains.customers.infrastructure import models as customer_models  # noqa: F401
from domains.invoicing.infrastructure import models as invoice_models  # noqa: F401
from domains.payments.infrastructure import models as payment_models  # noqa: F401
# from domains.settlements.infrastructure import models as settlement_models  # noqa: F401
from domains.users.infrastructure import models as users_models  # noqa: F401
from foundation.database.base import Base
from foundation.database.session import engine


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)

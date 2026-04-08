from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    MAIN_ADMIN = "main_admin"
    FRANCHISE_ADMIN = "franchise_admin"
    FRANCHISE_STAFF_MEMBER = "franchise_staff_member"


MAIN_ADMIN_ROLE = UserRole.MAIN_ADMIN.value
FRANCHISE_ADMIN_ROLE = UserRole.FRANCHISE_ADMIN.value
FRANCHISE_STAFF_ROLE = UserRole.FRANCHISE_STAFF_MEMBER.value

# Franchise
VIEW_FRANCHISES = "franchise:view"
CREATE_FRANCHISES = "franchise:create"
UPDATE_FRANCHISES = "franchise:update"
ACTIVATE_FRANCHISES = "franchise:activate"
DEACTIVATE_FRANCHISES = "franchise:deactivate"
VIEW_FRANCHISE_PERFORMANCE = "franchise:performance_view"

# Franchise commission policy
VIEW_FRANCHISE_COMMISSION_POLICIES = "franchise_commission_policy:view"
CREATE_FRANCHISE_COMMISSION_POLICIES = "franchise_commission_policy:create"

# Franchise timing
VIEW_FRANCHISE_TIMINGS = "franchise_timing:view"
UPDATE_FRANCHISE_TIMINGS = "franchise_timing:update"

# Franchise review
VIEW_FRANCHISE_REVIEWS = "franchise_review:view"
CREATE_FRANCHISE_REVIEWS = "franchise_review:create"
UPDATE_FRANCHISE_REVIEWS = "franchise_review:update"

# Service
VIEW_SERVICES = "service:view"
CREATE_SERVICES = "service:create"
ACTIVATE_SERVICES = "service:activate"
DEACTIVATE_SERVICES = "service:deactivate"
VIEW_SERVICE_POPULARITY = "service:popularity_view"
VIEW_SERVICE_ANALYTICS = "service:analytics_view"

# User
VIEW_USERS = "user:view"
VIEW_USER_PERMISSIONS = "user:view_permissions"
CREATE_USERS = "user:create"
UPDATE_USER_PROFILE = "user:update_profile"
UPDATE_USER_ACCESS = "user:update_access"
UPDATE_USER_PERMISSIONS = "user:update_permissions"
ACTIVATE_USERS = "user:activate"
DEACTIVATE_USERS = "user:deactivate"
RESET_USER_PASSWORD = "user:reset_password"
VIEW_USER_PERFORMANCE = "user:performance_view"

# Customer
VIEW_CUSTOMERS = "customer:view"
CREATE_CUSTOMERS = "customer:create"
UPDATE_CUSTOMERS = "customer:update"
VIEW_CUSTOMER_HISTORY = "customer:history_view"

# Vehicle
VIEW_VEHICLES = "vehicle:view"
CREATE_VEHICLES = "vehicle:create"
UPDATE_VEHICLES = "vehicle:update"

# Booking
CREATE_BOOKING = "booking:create"
VIEW_BOOKINGS = "booking:view"
UPDATE_BOOKINGS = "booking:update"
MANAGE_BOOKING_ITEMS = "booking:manage_items"
VIEW_BOOKING_ITEMS = "booking_item:view"

# Invoice
CREATE_INVOICE = "invoice:create"
VIEW_INVOICES = "invoice:view"
CREATE_NON_GST_INVOICE = "invoice:create_without_gst"
CREATE_INVOICE_PAYMENTS = "invoice:payment_create"
UPDATE_INVOICE_GST = "invoice:gst_update"
MANUAL_UPDATE_INVOICE_PAYMENT_STATUS = "invoice:manual_payment_status_update"

# Payment
RECORD_PAYMENT = "payment:record"
VIEW_PAYMENTS = "payment:view"
UPDATE_PAYMENT_REFERENCE = "payment:update_reference"

# Reports
VIEW_REPORT_OVERVIEW = "report:overview_view"
VIEW_REVENUE_DAILY_SUMMARY = "report:revenue_daily_summary_view"
VIEW_REVENUE_MONTHLY_OVERVIEW = "report:revenue_monthly_overview_view"
VIEW_REVENUE_WEEKLY_OVERVIEW = "report:revenue_weekly_overview_view"
VIEW_REVENUE_BY_SERVICE = "report:revenue_by_service_view"
VIEW_REVENUE_BY_FRANCHISE = "report:revenue_by_franchise_view"
VIEW_FRANCHISE_NETWORK_SUMMARY = "report:franchise_network_summary_view"
VIEW_FRANCHISES_BY_PERFORMANCE = "report:franchises_by_performance_view"
VIEW_FRANCHISE_PERFORMANCE_REPORT = "report:franchise_performance_view"
VIEW_CUSTOMER_INSIGHTS = "report:customer_insights_view"
EXPORT_REPORT_PDF = "report:export_pdf"
EXPORT_REPORT_EXCEL = "report:export_excel"

# Settlement
SETTLE_DAY = "settlement:close"

# Compatibility aliases kept only while unmigrated modules still depend on
# broader permission names from the older auth model.
MANAGE_FRANCHISES = "franchise:manage"
MANAGE_USERS = "user:manage"
VIEW_REPORTS = "report:view"
VIEW_GLOBAL_REPORTS = "report:view_global"

ALL_PERMISSION_CODES = {
    # Franchise
    VIEW_FRANCHISES,
    CREATE_FRANCHISES,
    UPDATE_FRANCHISES,
    ACTIVATE_FRANCHISES,
    DEACTIVATE_FRANCHISES,
    VIEW_FRANCHISE_PERFORMANCE,
    # Franchise commission policy
    VIEW_FRANCHISE_COMMISSION_POLICIES,
    CREATE_FRANCHISE_COMMISSION_POLICIES,
    # Franchise timing
    VIEW_FRANCHISE_TIMINGS,
    UPDATE_FRANCHISE_TIMINGS,
    # Franchise review
    VIEW_FRANCHISE_REVIEWS,
    CREATE_FRANCHISE_REVIEWS,
    UPDATE_FRANCHISE_REVIEWS,
    # Service
    VIEW_SERVICES,
    CREATE_SERVICES,
    ACTIVATE_SERVICES,
    DEACTIVATE_SERVICES,
    VIEW_SERVICE_POPULARITY,
    VIEW_SERVICE_ANALYTICS,
    # User
    VIEW_USERS,
    VIEW_USER_PERMISSIONS,
    CREATE_USERS,
    UPDATE_USER_PROFILE,
    UPDATE_USER_ACCESS,
    UPDATE_USER_PERMISSIONS,
    ACTIVATE_USERS,
    DEACTIVATE_USERS,
    RESET_USER_PASSWORD,
    VIEW_USER_PERFORMANCE,
    # Customer
    CREATE_CUSTOMERS,
    UPDATE_CUSTOMERS,
    VIEW_CUSTOMER_HISTORY,
    # Vehicle
    VIEW_VEHICLES,
    CREATE_VEHICLES,
    UPDATE_VEHICLES,
    # Booking
    UPDATE_BOOKINGS,
    MANAGE_BOOKING_ITEMS,
    VIEW_BOOKING_ITEMS,
    # Invoice
    CREATE_INVOICE_PAYMENTS,
    UPDATE_INVOICE_GST,
    MANUAL_UPDATE_INVOICE_PAYMENT_STATUS,
    # Payment
    UPDATE_PAYMENT_REFERENCE,
    # Reports
    VIEW_REPORT_OVERVIEW,
    VIEW_REVENUE_DAILY_SUMMARY,
    VIEW_REVENUE_MONTHLY_OVERVIEW,
    VIEW_REVENUE_WEEKLY_OVERVIEW,
    VIEW_REVENUE_BY_SERVICE,
    VIEW_REVENUE_BY_FRANCHISE,
    VIEW_FRANCHISE_NETWORK_SUMMARY,
    VIEW_FRANCHISES_BY_PERFORMANCE,
    VIEW_FRANCHISE_PERFORMANCE_REPORT,
    VIEW_CUSTOMER_INSIGHTS,
    EXPORT_REPORT_PDF,
    EXPORT_REPORT_EXCEL,
    # Settlement
    SETTLE_DAY,
    # Compatibility aliases
    CREATE_BOOKING,
    VIEW_BOOKINGS,
    CREATE_INVOICE,
    VIEW_INVOICES,
    CREATE_NON_GST_INVOICE,
    VIEW_CUSTOMERS,
    MANAGE_FRANCHISES,
    MANAGE_USERS,
    RECORD_PAYMENT,
    VIEW_PAYMENTS,
    VIEW_REPORTS,
    VIEW_GLOBAL_REPORTS,
}

FRANCHISE_SCOPED_REPORT_PERMISSIONS = {
    VIEW_REPORTS,
    VIEW_REPORT_OVERVIEW,
    VIEW_REVENUE_DAILY_SUMMARY,
    VIEW_REVENUE_MONTHLY_OVERVIEW,
    VIEW_REVENUE_WEEKLY_OVERVIEW,
    VIEW_REVENUE_BY_SERVICE,
    VIEW_CUSTOMER_INSIGHTS,
    VIEW_USER_PERFORMANCE,
    VIEW_SERVICE_ANALYTICS,
    VIEW_SERVICE_POPULARITY,
    EXPORT_REPORT_PDF,
    EXPORT_REPORT_EXCEL,
}

DEFAULT_ROLE_PERMISSIONS = {
    UserRole.MAIN_ADMIN: set(ALL_PERMISSION_CODES),
    UserRole.FRANCHISE_ADMIN: {
        # Legacy
        CREATE_BOOKING,
        VIEW_BOOKINGS,
        CREATE_INVOICE,
        VIEW_INVOICES,
        VIEW_CUSTOMERS,
        MANAGE_USERS,
        RECORD_PAYMENT,
        VIEW_PAYMENTS,
        VIEW_REPORTS,
        SETTLE_DAY,
        # Franchise
        VIEW_FRANCHISES,
        VIEW_FRANCHISE_TIMINGS,
        UPDATE_FRANCHISE_TIMINGS,
        VIEW_FRANCHISE_REVIEWS,
        CREATE_FRANCHISE_REVIEWS,
        UPDATE_FRANCHISE_REVIEWS,
        # Service
        VIEW_SERVICES,
        VIEW_SERVICE_POPULARITY,
        VIEW_SERVICE_ANALYTICS,
        # User
        VIEW_USERS,
        CREATE_USERS,
        UPDATE_USER_PROFILE,
        ACTIVATE_USERS,
        DEACTIVATE_USERS,
        RESET_USER_PASSWORD,
        VIEW_USER_PERFORMANCE,
        # Customer
        CREATE_CUSTOMERS,
        UPDATE_CUSTOMERS,
        VIEW_CUSTOMER_HISTORY,
        # Vehicle
        VIEW_VEHICLES,
        CREATE_VEHICLES,
        UPDATE_VEHICLES,
        # Booking
        UPDATE_BOOKINGS,
        MANAGE_BOOKING_ITEMS,
        VIEW_BOOKING_ITEMS,
        # Invoice
        CREATE_INVOICE_PAYMENTS,
        # Payment
        UPDATE_PAYMENT_REFERENCE,
        # Reports
        *FRANCHISE_SCOPED_REPORT_PERMISSIONS,
    },
    UserRole.FRANCHISE_STAFF_MEMBER: {
        # Legacy
        CREATE_BOOKING,
        VIEW_BOOKINGS,
        CREATE_INVOICE,
        VIEW_INVOICES,
        VIEW_CUSTOMERS,
        RECORD_PAYMENT,
        VIEW_PAYMENTS,
        VIEW_REPORTS,
        # Franchise
        VIEW_FRANCHISES,
        VIEW_FRANCHISE_TIMINGS,
        VIEW_FRANCHISE_REVIEWS,
        CREATE_FRANCHISE_REVIEWS,
        UPDATE_FRANCHISE_REVIEWS,
        # Service
        VIEW_SERVICES,
        VIEW_SERVICE_POPULARITY,
        VIEW_SERVICE_ANALYTICS,
        # User
        VIEW_USERS,
        UPDATE_USER_PROFILE,
        # Customer
        CREATE_CUSTOMERS,
        UPDATE_CUSTOMERS,
        VIEW_CUSTOMER_HISTORY,
        # Vehicle
        VIEW_VEHICLES,
        CREATE_VEHICLES,
        UPDATE_VEHICLES,
        # Booking
        UPDATE_BOOKINGS,
        MANAGE_BOOKING_ITEMS,
        VIEW_BOOKING_ITEMS,
        # Invoice
        CREATE_INVOICE_PAYMENTS,
        # Payment
        UPDATE_PAYMENT_REFERENCE,
        # Reports
        *FRANCHISE_SCOPED_REPORT_PERMISSIONS,
    },
}

VALID_PERMISSION_CODES = {
    permission
    for permissions in DEFAULT_ROLE_PERMISSIONS.values()
    for permission in permissions
}


def resolve_effective_permissions(
    role: UserRole,
    extra_permissions: list[str] | None,
    revoked_permissions: list[str] | None,
) -> set[str]:
    base_permissions = set(DEFAULT_ROLE_PERMISSIONS.get(role, set()))
    allowed_extras = {
        permission
        for permission in extra_permissions or []
        if permission in VALID_PERMISSION_CODES
    }
    blocked_permissions = set(revoked_permissions or [])
    return (base_permissions | allowed_extras) - blocked_permissions

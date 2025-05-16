import logging

AUDIT_LEVEL = 18
API_LEVEL = 19


# Only add the level if it doesn't already exist
if not hasattr(logging, "AUDIT"):
    logging.addLevelName(AUDIT_LEVEL, "AUDIT")

    # Add the audit method to Logger class
    def audit(self, message, *args, **kwargs):
        if self.isEnabledFor(AUDIT_LEVEL):
            self._log(AUDIT_LEVEL, message, args, **kwargs)

    logging.Logger.audit = audit
else:
    # Use existing AUDIT level if it's already defined
    AUDIT_LEVEL = logging.AUDIT

if not hasattr(logging, "API"):
    logging.addLevelName(API_LEVEL, "API")

    # Add the audit method to Logger class
    def api(self, message, *args, **kwargs):
        if self.isEnabledFor(API_LEVEL):
            self._log(API_LEVEL, message, args, **kwargs)

    logging.Logger.api = api
else:
    # Use existing API level if it's already defined
    API_LEVEL = logging.API

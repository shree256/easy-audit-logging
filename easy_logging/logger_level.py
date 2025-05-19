import logging

AUDIT = 21
API = 22


# Only add the level if it doesn't already exist
if not hasattr(logging, "AUDIT"):
    logging.addLevelName(AUDIT, "AUDIT")

    # Add the audit method to Logger class
    def audit(self, message, *args, **kwargs):
        if self.isEnabledFor(AUDIT):
            self._log(AUDIT, message, args, **kwargs)

    logging.Logger.audit = audit
else:
    # Use existing AUDIT level if it's already defined
    AUDIT = logging.AUDIT

if not hasattr(logging, "API"):
    logging.addLevelName(API, "API")

    # Add the audit method to Logger class
    def api(self, message, *args, **kwargs):
        if self.isEnabledFor(API):
            self._log(API, message, args, **kwargs)

    logging.Logger.api = api
else:
    # Use existing API level if it's already defined
    API = logging.API

import logging

AUDIT_LEVEL = 15

# Only add the level if it doesn't already exist
if not hasattr(logging, "AUDIT"):
    logging.addLevelName(AUDIT_LEVEL, "AUDIT")

    # Add the audit method to Logger class
    def audit(self, message, *args, **kwargs):
        """Custom audit logging method"""
        if self.isEnabledFor(AUDIT_LEVEL):
            self._log(AUDIT_LEVEL, message, args, **kwargs)

    logging.Logger.audit = audit
else:
    # Use existing AUDIT level if it's already defined
    AUDIT_LEVEL = logging.AUDIT

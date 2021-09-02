from django.contrib.sessions.backends.db import SessionStore
from django.db import connections
from django.utils.safestring import mark_safe

from . import is_versioned_model
from dolt.constants import DB_NAME, DOLT_DEFAULT_BRANCH, GLOBAL_DB
from dolt.models import Branch
from dolt.utils import DoltError, is_dolt_model, active_branch


class GlobalStateRouter:
    """
    TODO
    """

    global_db = GLOBAL_DB

    def db_for_read(self, model, **hints):
        """
        Directs read queries to the global state db for non-versioned models.
        Versioned models use the 'default' database and the Dolt branch that
        was checked out in `DoltBranchMiddleware`.
        """
        if active_branch() == DOLT_DEFAULT_BRANCH:
            # If primary branch is active, send all queries
            # to "global", even for versioned models
            return self.global_db

        if is_versioned_model(model):
            return None

        return self.global_db

    def db_for_write(self, model, **hints):
        """
        Directs write queries to the global state db for non-versioned models.
        Versioned models use the 'default' database and the Dolt branch that
        was checked out in `DoltBranchMiddleware`.
        Prevents writes of non-versioned models on non-primary branches.
        """
        if active_branch() == DOLT_DEFAULT_BRANCH:
            # If primary branch is active, send all queries
            # to "global", even for versioned models
            return self.global_db

        if is_dolt_model(model):
            # Dolt models can be created or edited from any branch.
            # Edits will be applied to the "main"
            return self.global_db

        if is_versioned_model(model):
            return None

        if self.branch_is_not_primary():
            breakpoint()
            # non-versioned models can only be edited on "main"
            raise DoltError(
                mark_safe(
                    f"""Error writing <strong>{model.__name__}</strong>: non-versioned models 
                    must be written on branch <strong>"{DOLT_DEFAULT_BRANCH}"</strong>."""
                )
            )

        return self.global_db

    def allow_relation(self, obj1, obj2, **hints):
        return True

    @staticmethod
    def branch_is_not_primary():
        return active_branch() != DOLT_DEFAULT_BRANCH

    @staticmethod
    def is_pr_model(model):
        """
        Return True is `model` is related to PullRequests.
        """
        pr_models = {
            "dolt": {
                "pullrequest": True,
                "pullrequestreviewcomment": True,
                "pullrequestreview": True,
            },
        }
        return bool(query_registry(model, pr_models))

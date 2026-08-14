"""The Status values, written down once.

They were written down four times instead: `VALID_STATUSES` in
`notion_push/properties.py`, `DONE_STATUSES` and `ACTIVE_STATUSES` in
`notion_ops.py` — the second of which was defined and never read — and the same
strings inline in the ops report's own comparisons. Nothing referred to
anything else, so adding a value meant finding every copy, and a copy missed is
not a crash: rows in the new status are neither done nor active, and they drop
out of every count without appearing anywhere as a problem.

This module only moves the definitions together. It does not decide anything
the records/work-items design has open — whether `Deployed` should mean shipped
or merely finished is still a question, and it is answered here by leaving the
current meaning exactly as it was.
"""

#: Every value the Status property accepts, in workflow order.
ORDERED = ("Discussion", "Design", "Implementation", "Testing", "Deployed")

#: Membership test for input validation. Order is irrelevant here.
VALID = frozenset(ORDERED)

#: Terminal. The one status that ends a work item.
DONE = frozenset({"Deployed"})

#: Opened but not yet being built. The ops report treats a parent in one of
#: these as behind its children, which is the only question it is asked.
EARLY = ("Discussion", "Design")

#: Being worked on right now, as opposed to merely opened. The ops report uses
#: this to decide which items owe a next action, which `EARLY` ones do not.
IN_PROGRESS = ("Implementation", "Testing")

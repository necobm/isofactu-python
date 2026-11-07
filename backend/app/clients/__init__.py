"""Clients module: the tenant's client directory.

Independent from invoicing: an invoice never references a client. When an invoice is
created the chosen client's data is *copied* into a `Subject` of the Invoicing module.
"""

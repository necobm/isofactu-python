"""HTTP endpoints of the Clients module (`/api/client`), for the logged-in tenant."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.accounts.deps import CurrentTenant, SessionDep
from app.clients.models import Client
from app.clients.repository import ClientRepository
from app.clients.schemas import ClientCollection, ClientCreate, ClientRead, ClientUpdate
from app.invoicing.value_objects import Address, IdentificationDocument

LimitParam = Annotated[int, Query(ge=1, le=200, description="Page size")]
OffsetParam = Annotated[int, Query(ge=0, description="Number of items to skip")]
SearchParam = Annotated[
    str | None, Query(max_length=100, description="Match on the name or the document number")
]

client_router = APIRouter(prefix="/client", tags=["Clients"])


@client_router.get(
    "",
    response_model=ClientCollection,
    summary="List clients",
    description="Clients ordered by name, optionally filtered with `?q=` (name or document).",
)
async def list_clients(
    tenant: CurrentTenant,
    session: SessionDep,
    q: SearchParam = None,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
) -> ClientCollection:
    repo = ClientRepository(session, tenant.id)
    items = await repo.find_all(search=q, limit=limit, offset=offset)
    return ClientCollection(
        items=[ClientRead.model_validate(c) for c in items],
        total=await repo.count(search=q),
        limit=limit,
        offset=offset,
    )


@client_router.get("/{client_id}", response_model=ClientRead, summary="Get a client")
async def get_client(tenant: CurrentTenant, client_id: int, session: SessionDep) -> Client:
    return await _find(client_id, session, tenant.id)


@client_router.post(
    "",
    response_model=ClientRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a client",
)
async def create_client(
    tenant: CurrentTenant, payload: ClientCreate, session: SessionDep
) -> Client:
    client = Client(owner=tenant, **_fields(payload))
    await ClientRepository(session, tenant.id).add(client)
    await session.commit()
    return client


@client_router.put(
    "/{client_id}",
    response_model=ClientRead,
    summary="Update a client",
    description="Replaces the client. Invoices already created with it are not affected.",
)
async def update_client(
    tenant: CurrentTenant, client_id: int, payload: ClientUpdate, session: SessionDep
) -> Client:
    client = await _find(client_id, session, tenant.id)
    for field, value in _fields(payload).items():
        setattr(client, field, value)
    await session.commit()
    return client


@client_router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a client",
    description="Invoices created with the client keep their copy of its data.",
)
async def delete_client(tenant: CurrentTenant, client_id: int, session: SessionDep) -> None:
    repo = ClientRepository(session, tenant.id)
    await repo.delete(await _find(client_id, session, tenant.id))
    await session.commit()


async def _find(client_id: int, session, owner_id: int) -> Client:
    client = await ClientRepository(session, owner_id).find(client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client


def _fields(payload: ClientCreate | ClientUpdate) -> dict:
    return {
        "full_name": payload.full_name,
        "document": IdentificationDocument(**payload.document.model_dump()),
        "address": Address(**payload.address.model_dump()),
    }

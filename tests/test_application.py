from litestar import Litestar, Request, route
from litestar.datastructures import MutableScopeHeaders as MutableHeaders
from litestar.middleware import DefineMiddleware as Middleware
from litestar.response import Response
from litestar.testing import TestClient
from litestar.types import ASGIApp, Message, Receive, Scope, Send
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

from sqladmin import Admin, ModelView
from tests.common import sync_engine as engine

Base = declarative_base()  # type: ignore


class DataModel(Base):
    __tablename__ = "datamodel"
    id = Column(Integer, primary_key=True)
    data = Column(String)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(32), default="SQLAdmin")


def test_application_title() -> None:
    app = Litestar()
    Admin(app=app, engine=engine)

    with TestClient(app) as client:
        response = client.get("/admin")

    assert response.status_code == 200
    assert "<h3>Admin</h3>" in response.text
    assert "<title>Admin</title>" in response.text


def test_application_logo() -> None:
    app = Litestar()
    Admin(
        app=app,
        engine=engine,
        logo_url="https://example.com/logo.svg",
        base_url="/dashboard",
    )

    with TestClient(app) as client:
        response = client.get("/dashboard")

    assert response.status_code == 200
    assert (
        '<img src="https://example.com/logo.svg" width="64" height="64"'
        in response.text
    )


def test_middlewares() -> None:
    class CorrelationIdMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            async def send_wrapper(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers.add("X-Correlation-ID", "UUID")
                await send(message)

            await self.app(scope, receive, send_wrapper)

    app = Litestar()
    Admin(
        app=app,
        engine=engine,
        middlewares=[Middleware(CorrelationIdMiddleware)],
    )

    with TestClient(app) as client:
        response = client.get("/admin")

    assert response.status_code == 200
    assert "x-correlation-id" in response.headers


def test_get_save_redirect_url():
    @route("/x/{identity:str}", http_method=["POST"])
    async def index(request: Request) -> Response:
        obj = User(id=1)
        form_data = await request.form()
        url = admin.get_save_redirect_url(request, form_data, admin.views[0], obj)
        return Response(str(url))

    app = Litestar(route_handlers=[index])
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        save_as = True

    admin.add_view(UserAdmin)

    client = TestClient(app)

    response = client.post("/x/user", data={"save": "Save"})
    assert response.text == "http://testserver/admin/user/list"

    response = client.post("/x/user", data={"save": "Save and continue editing"})
    assert response.text == "http://testserver/admin/user/edit/1"

    response = client.post("/x/user", data={"save": "Save as new"})
    assert response.text == "http://testserver/admin/user/edit/1"

    response = client.post("/x/user", data={"save": "Save and add another"})
    assert response.text == "http://testserver/admin/user/create"


def test_build_category_menu():
    app = Litestar()
    admin = Admin(app=app, engine=engine)

    class UserAdmin(ModelView, model=User):
        category = "Accounts"

    admin.add_view(UserAdmin)

    admin._menu.items.pop().name = "Accounts"


def test_normalize_wtform_fields() -> None:
    app = Litestar()
    admin = Admin(app=app, engine=engine)

    class DataModelAdmin(ModelView, model=DataModel):
        ...

    datamodel = DataModel(id=1, data="abcdef")
    admin.add_view(DataModelAdmin)
    assert admin._normalize_wtform_data(datamodel) == {"data_": "abcdef"}


def test_denormalize_wtform_fields() -> None:
    app = Litestar()
    admin = Admin(app=app, engine=engine)

    class DataModelAdmin(ModelView, model=DataModel):
        ...

    datamodel = DataModel(id=1, data="abcdef")
    admin.add_view(DataModelAdmin)
    assert admin._denormalize_wtform_data({"data_": "abcdef"}, datamodel) == {
        "data": "abcdef"
    }

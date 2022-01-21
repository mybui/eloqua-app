from flask import Request, current_app


class _BaseRequestMeta(type):
    """
    Metaclass for _BaseRequest. Appends all of the fields from the class' nested Meta class and its parents to
    __all_fields.
    """
    __all_fields = set()

    def __new__(mcs, name, bases, attrs):
        # Get the Meta class.
        meta = attrs.get("Meta", None)
        append = True
        # Check for the append attribute, i.e. whether the class should append the fields or just replace them entirely.
        if hasattr(meta, "append"):
            append = meta.append
        # Check for the fields attribute which tells which fields to use.
        if hasattr(meta, "fields"):
            if append:
                mcs.__all_fields = mcs.__all_fields.union(meta.fields)
            else:
                mcs.__all_fields = meta.fields

        new = super(_BaseRequestMeta, mcs).__new__(mcs, name, bases, attrs)
        new._all_fields = mcs.__all_fields

        return new


class _BaseRequest(metaclass=_BaseRequestMeta):
    """
    A helper class for accessing a cloud app request's args.

    It takes a flask.Request object and any extra arguments and maps the request's arguments and the extra args to the
    fields listed in Meta class' fields attribute.

    All of the fields are optional, so if you're not absolutely sure that a field has a value, check for None.
    """

    class Meta:
        fields = ("user_id", "user_name", "user_culture", "install_id", "site_id", "site_name", "app_id")

    user_name: str
    user_id: int
    user_culture: str
    app_id: str
    install_id: str
    site_id: int
    site_name: str

    _all_fields: set

    def __init__(self, request: Request, **additional_args):
        all_args = {**request.args, **additional_args}
        for field in self._all_fields:
            self.__setattr__(field, all_args.get(field, None))

    def as_dict(self, include_nones=False):
        output = {field: self.__getattribute__(field) for field in self._all_fields}
        if not include_nones:
            return {k: v for (k, v) in output.items() if v is not None}
        return output


class AppRequest(_BaseRequest):
    """
    An app level request. Almost identical to _BaseRequest.
    """

    class Meta:
        fields = ("callback_url",)

    callback_url: str


class ServiceRequest(_BaseRequest):
    """
    A service level request. This covers all of the services, i.e. action, decision, feeder, content, menu and firehose
    services.
    """

    class Meta:
        fields = (
            "instance_id", "asset_id", "asset_name", "asset_type", "execution_id", "entity_type", "custom_object_id",
            "original_install_id", "original_instance_id", "original_asset_id", "original_asset_name", "render_type",
            "is_preview", "visitor_id", "event_type"
        )

    instance_id: str
    asset_id: str
    asset_name: str
    asset_type: str
    execution_id: str
    entity_type: str
    custom_object_id: str
    original_install_id: str
    original_instance_id: str
    original_asset_id: str
    original_asset_name: str
    event_type: str

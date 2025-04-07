from rest_framework.response import Response


def build_response(*, status_code, message, data=None):
    data = {} if data is None else data
    return Response(
        status=status_code, data={"status": True, "message": message, "data": data}
    )

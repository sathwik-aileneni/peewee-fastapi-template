from functools import wraps
from controller.cerebrus import CustomValidator
from logger.logging import LoggerUtil
from utils.exceptions import CustomBadRequest
from utils.contextvar import (
    get_request_json_post_payload,
    get_request_metadata,
    set_request_metadata,
    clear_request_metadata,
)
import asyncio
from typing import Dict, Type, Any
import uuid
from utils.contextvar import RequestMetadata
from concurrent.futures import ThreadPoolExecutor
import datetime


def validate_json_payload(payload_validation_schema: dict):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # default values
            is_validated = False
            v = None
            try:
                post_payload = get_request_json_post_payload()
                v = CustomValidator(
                    schema=payload_validation_schema,
                    allow_unknown=True,
                    require_all=True,
                )
                is_validated = v.validate(post_payload)
            except Exception as e:
                LoggerUtil.create_error_log(
                    "BAD_REQUEST_EXCEPTION: {}".format(e),
                )
                raise CustomBadRequest(detail="Invalid json payload")
            if not is_validated:
                LoggerUtil.create_error_log(
                    "BAD_REQUEST:Payload:{},Error:{}".format(post_payload, v.errors),
                )
                raise CustomBadRequest(
                    detail="Invalid payload", errors=v.errors if v else None
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def validate_query_params(func):
    # TODO :: Add the logic to validate the query params
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def singleton_class(cls):
    """
    await the class to be initialized
    class_object = await SingletonClass()
    class_object.method()


    if not awaited it will return a coroutine object
    class_object = SingletonClass()
    class_object.method() (fails with coroutine not having the method)
    """
    instances: Dict[Type, Any] = {}
    lock = asyncio.Lock()

    async def wrapper(*args, **kwargs):
        if cls not in instances:
            async with lock:
                # Double-checked locking pattern
                if cls not in instances:
                    instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return wrapper


executor = ThreadPoolExecutor(max_workers=4)  # or as needed


def run_in_background(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        current_metadata = get_request_metadata()
        new_thread_id = str(uuid.uuid4())
        new_metadata = RequestMetadata(
            api_id=current_metadata["api_id"], thread_id=new_thread_id
        )
        LoggerUtil.create_info_log(
            "Background job started with thread_id : {} and api_id : {}, timestamp :{}".format(
                new_thread_id, current_metadata["api_id"], datetime.datetime.now()
            )
        )

        def run_in_thread():
            try:
                set_request_metadata(new_metadata.to_dict())
                return func(*args, **kwargs)
            except Exception as e:
                LoggerUtil.create_error_log(
                    "Background job failed with thread_id : {} and api_id : {}, timestamp :{}".format(
                        new_thread_id,
                        current_metadata["api_id"],
                        datetime.datetime.now(),
                    )
                )
                raise e
            finally:
                # Clear context when job is done
                clear_request_metadata()

        if asyncio.iscoroutinefunction(func):

            def async_runner():
                try:
                    set_request_metadata(new_metadata.to_dict())
                    asyncio.run(func(*args, **kwargs))
                except Exception:
                    LoggerUtil.create_error_log(
                        "Background job failed with thread_id : {} and api_id : {}, timestamp :{}".format(
                            new_thread_id,
                            current_metadata["api_id"],
                            datetime.datetime.now(),
                        )
                    )
                finally:
                    clear_request_metadata()

            executor.submit(async_runner)
        else:
            executor.submit(run_in_thread)

    return wrapper

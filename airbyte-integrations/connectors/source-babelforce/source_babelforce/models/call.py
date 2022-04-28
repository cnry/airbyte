#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#

from datetime import datetime
from typing import Optional, List

from pydantic import Field
from typing_extensions import Annotated

from source_babelforce.models.base_model import BaseModel


class CallAgent(BaseModel):
    id: Optional[Annotated[str, Field(max_length=32)]]
    name: Optional[Annotated[str, Field(max_length=256)]]
    number: Optional[int]


class CallBridged(BaseModel):
    id: Optional[Annotated[str, Field(max_length=32)]]
    name: Optional[Annotated[str, Field(max_length=256)]]
    number: Optional[int]
    queueId: Optional[Annotated[str, Field(max_length=32, nullable=True)]]
    queueName: Optional[Annotated[str, Field(max_length=256)]]
    agent: Optional[CallAgent]


class CallRecordingFile(BaseModel):
    id: Annotated[str, Field(max_length=32)]
    state: Optional[Annotated[str, Field(max_length=256)]]
    name: Optional[Annotated[str, Field(max_length=256)]]
    size: Optional[int]
    contentType: Optional[Annotated[str, Field(max_length=256)]]


class CallRecording(BaseModel):
    id: Annotated[str, Field(max_length=32)]
    dateCreated: datetime
    lastUpdated: datetime
    duration: int
    url: str
    tags: List[str]
    file: Optional[CallRecordingFile]
    state: Annotated[str, Field(max_length=256)]
    agent: CallAgent

    
class Call(BaseModel):
    id: Annotated[str, Field(max_length=32)]
    parentId: Optional[Annotated[str, Field(max_length=32)]]
    sessionId: Annotated[str, Field(max_length=32)]
    conversationId: Annotated[str, Field(max_length=32)]
    dateCreated: datetime
    dateEstablished: Optional[datetime]
    dateFinished: Optional[datetime]
    lastUpdated: datetime
    state: Annotated[str, Field(max_length=256)]
    finishReason: Annotated[str, Field(max_length=256)]
    from_: Optional[int]
    to: Optional[int]
    type: Annotated[str, Field(max_length=256)]
    source: Annotated[str, Field(max_length=256)]
    domain: Annotated[str, Field(max_length=256)]
    duration: Optional[int]
    anonymous: Optional[bool]
    recordings: Optional[List[CallRecording]]
    bridged: Optional[CallBridged]

    class Config:
        fields = {"from_": "from"}

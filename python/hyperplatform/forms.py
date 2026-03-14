from typing import Optional, List, Union, Any, Literal

from pydantic import BaseModel


class BaseFormElement(BaseModel):
    id: str
    label: Optional[str] = None
    label_position: Literal['top', 'left', 'right', 'bottom'] = 'top'
    required: bool = False
    initial_value: Optional[Any] = None


class TextInput(BaseFormElement):
    type: Literal['text'] = 'text'
    placeholder: Optional[str] = None
    validation: Optional[str] = None


class DropDownOption(BaseModel):
    value: Union[str, int]
    label: str


class DropDown(BaseFormElement):
    type: Literal['dropdown'] = 'dropdown'
    placeholder: Optional[str] = None
    options: List[DropDownOption]
    multiple: bool = False
    selected_value: Optional[Union[str, int, List[Union[str, int]]]] = None


class RadioOption(BaseModel):
    value: Union[str, int]
    label: str


class Radio(BaseFormElement):
    type: Literal['radio'] = 'radio'
    options: List[RadioOption]
    selected_value: Optional[Union[str, int]] = None


class CheckBox(BaseFormElement):
    type: Literal['checkbox'] = 'checkbox'
    selected_value: bool = False


class DatePicker(BaseFormElement):
    type: Literal['date'] = 'date'
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    format: str = "DD.MM.YYYY"


class TimePicker(BaseFormElement):
    type: Literal['time'] = 'time'
    min_time: Optional[str] = None
    max_time: Optional[str] = None
    format: str = "HH:mm"


class SubmitButton(BaseModel):
    text: str = "Submit"
    align: Literal['left', 'right', 'center'] = 'center'


FormElement = Union[TextInput, DropDown, Radio, CheckBox, DatePicker, TimePicker]


class FormRow(BaseModel):
    elements: List[FormElement]
    align: Literal['left', 'right', 'center', 'space-between'] = 'left'


class FormData(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    bg_color: Optional[str] = None
    primary_color: Optional[str] = None
    rows: List[FormRow]
    submit_button: SubmitButton = SubmitButton()


class FormSubmission(BaseModel):
    values: dict[str, Any]

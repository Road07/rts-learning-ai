extends Control

# Headless compatibility endpoint for the controller. No mod/chat panel is built.
var status_line: Label

func _ready() -> void:
	mouse_filter=Control.MOUSE_FILTER_IGNORE
	status_line=Label.new()
	add_child(status_line)
	hide()
	set_process(false)

func set_status(_active: bool, _decisions: int, _orders: int, _choice: String, _count: int) -> void:
	hide()

func add_message(_message: Dictionary, _faction: String, _body: String, _frame: int) -> void:
	pass

func clear_messages() -> void:
	pass

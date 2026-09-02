import time
import uuid
import json
import math
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from app.config import settings
from app.schemas.tools import ToolDefinition, ParameterDefinition, ToolExecutionResponse, ToolExecutionLogEntry

logger = logging.getLogger("sovereignx")

# Definition of Tool Registry
class LocalToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self.log_path = Path(settings.DOCUMENT_STORAGE_PATH).resolve().parent / "logs" / "tool_executions.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._register_default_tools()

    def register_tool(self, name: str, description: str, parameters: Dict[str, ParameterDefinition], func: Callable):
        self._tools[name] = {
            "definition": ToolDefinition(
                name=name,
                description=description,
                parameters=parameters
            ),
            "func": func
        }

    def list_tools(self) -> List[ToolDefinition]:
        return [t["definition"] for t in self._tools.values()]

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        return self._tools.get(name)

    def log_execution(self, entry: ToolExecutionLogEntry):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to write tool execution log: {e}")

    def get_logs(self, limit: int = 50) -> List[ToolExecutionLogEntry]:
        if not self.log_path.exists():
            return []
        
        entries = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # Read from latest to oldest
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        entries.append(ToolExecutionLogEntry(**json.loads(line)))
                        if len(entries) >= limit:
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Failed to read tool execution logs: {e}")
            
        return entries

    def execute(self, tool_name: str, arguments: Dict[str, Any], context_id: Optional[str] = None) -> ToolExecutionResponse:
        execution_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"
        start_time = time.perf_counter()
        
        tool = self.get_tool(tool_name)
        if not tool:
            duration = (time.perf_counter() - start_time) * 1000.0
            resp = ToolExecutionResponse(
                tool_name=tool_name,
                outputs={},
                status="failed",
                error=f"Tool '{tool_name}' is not registered.",
                execution_log_id=execution_id,
                duration_ms=round(duration, 2),
                context_id=context_id
            )
            log_entry = ToolExecutionLogEntry(
                id=execution_id,
                timestamp=timestamp,
                tool_name=tool_name,
                inputs=arguments,
                outputs=None,
                status="failed",
                error=resp.error,
                duration_ms=resp.duration_ms,
                context_id=context_id
            )
            self.log_execution(log_entry)
            return resp

        # Validate arguments against parameter schema
        validated_args = {}
        definition = tool["definition"]
        try:
            for param_name, param_def in definition.parameters.items():
                if param_name not in arguments:
                    if param_def.required:
                        raise ValueError(f"Missing required parameter: {param_name}")
                    validated_args[param_name] = param_def.default
                else:
                    val = arguments[param_name]
                    # Simple type coercion / validation
                    if param_def.type == "float":
                        try:
                            validated_args[param_name] = float(val)
                        except (ValueError, TypeError):
                            raise ValueError(f"Parameter '{param_name}' must be a float.")
                    elif param_def.type == "int":
                        try:
                            validated_args[param_name] = int(val)
                        except (ValueError, TypeError):
                            raise ValueError(f"Parameter '{param_name}' must be an integer.")
                    elif param_def.type == "list[float]":
                        if not isinstance(val, list):
                            raise ValueError(f"Parameter '{param_name}' must be a list of numbers.")
                        try:
                            validated_args[param_name] = [float(x) for x in val]
                        except (ValueError, TypeError):
                            raise ValueError(f"Parameter '{param_name}' must be a list containing only numbers.")
                    elif param_def.type == "str":
                        validated_args[param_name] = str(val)
                        if param_def.options and validated_args[param_name] not in param_def.options:
                            raise ValueError(
                                f"Parameter '{param_name}' value '{val}' not in allowed options: {param_def.options}"
                            )
                    else:
                        validated_args[param_name] = val
            
            # Execute actual function
            outputs = tool["func"](**validated_args)
            duration = (time.perf_counter() - start_time) * 1000.0
            
            resp = ToolExecutionResponse(
                tool_name=tool_name,
                outputs=outputs,
                status="success",
                execution_log_id=execution_id,
                duration_ms=round(duration, 2),
                context_id=context_id
            )
            log_entry = ToolExecutionLogEntry(
                id=execution_id,
                timestamp=timestamp,
                tool_name=tool_name,
                inputs=arguments,
                outputs=outputs,
                status="success",
                duration_ms=resp.duration_ms,
                context_id=context_id
            )
            self.log_execution(log_entry)
            return resp

        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000.0
            err_msg = str(e)
            logger.error(f"Error executing tool {tool_name}: {err_msg}")
            
            resp = ToolExecutionResponse(
                tool_name=tool_name,
                outputs={},
                status="failed",
                error=err_msg,
                execution_log_id=execution_id,
                duration_ms=round(duration, 2),
                context_id=context_id
            )
            log_entry = ToolExecutionLogEntry(
                id=execution_id,
                timestamp=timestamp,
                tool_name=tool_name,
                inputs=arguments,
                outputs=None,
                status="failed",
                error=err_msg,
                duration_ms=resp.duration_ms,
                context_id=context_id
            )
            self.log_execution(log_entry)
            return resp

    def _register_default_tools(self):
        # Tool 1: compare_reading_against_sop_limit
        self.register_tool(
            name="compare_reading_against_sop_limit",
            description="Compares a single operational sensor reading against a specified SOP threshold, returning whether the limit was exceeded, the absolute variance, and percentage deviation.",
            parameters={
                "reading_value": ParameterDefinition(type="float", description="The current sensor reading value"),
                "limit_value": ParameterDefinition(type="float", description="The SOP threshold limit"),
                "comparison_type": ParameterDefinition(
                    type="str", 
                    description="The comparison operator: 'greater_than' (limit is upper bound) or 'less_than' (limit is lower bound)",
                    options=["greater_than", "less_than"]
                ),
                "unit": ParameterDefinition(type="str", description="Unit of measurement (e.g. C, bar, mm/s)", required=False, default="")
            },
            func=compare_reading_against_sop_limit
        )

        # Tool 2: compute_variance_across_readings
        self.register_tool(
            name="compute_variance_across_readings",
            description="Calculates descriptive statistical variance, mean, standard deviation, minimum, maximum, and range across a series of numeric sensor readings.",
            parameters={
                "readings": ParameterDefinition(type="list[float]", description="A list of numerical sensor readings")
            },
            func=compute_variance_across_readings
        )

        # Tool 3: convert_units
        self.register_tool(
            name="convert_units",
            description="Safely converts operational measurements between standard units for temperature (C, F, K) and pressure (bar, psi, pa, kpa, mpa).",
            parameters={
                "value": ParameterDefinition(type="float", description="The value to convert"),
                "from_unit": ParameterDefinition(
                    type="str", 
                    description="Current unit of measurement",
                    options=["C", "F", "K", "bar", "psi", "pa", "kpa", "mpa"]
                ),
                "to_unit": ParameterDefinition(
                    type="str", 
                    description="Target unit of measurement",
                    options=["C", "F", "K", "bar", "psi", "pa", "kpa", "mpa"]
                )
            },
            func=convert_units
        )

        # Tool 4: verify_engineering_calculation
        self.register_tool(
            name="verify_engineering_calculation",
            description="Verifies an engineering scalar formula calculation against user-provided or extracted values using a safe AST evaluator and strict verification gate.",
            parameters={
                "text_input": ParameterDefinition(type="str", description="The raw free-text calculation prompt or formula input string")
            },
            func=verify_engineering_calculation
        )

        # Tool 5: evaluate_arithmetic_expression
        self.register_tool(
            name="evaluate_arithmetic_expression",
            description="Deterministically evaluates a plain arithmetic expression (already normalized to symbols, e.g. '10384 * 827') using the same safe AST evaluator as verify_engineering_calculation -- no LLM-based math involved.",
            parameters={
                "expression": ParameterDefinition(type="str", description="Normalized arithmetic expression string, e.g. '10384 * 827' or '(25 * 8) + 17'")
            },
            func=evaluate_arithmetic_expression
        )


# Default tool implementation functions

def compare_reading_against_sop_limit(
    reading_value: float, 
    limit_value: float, 
    comparison_type: str, 
    unit: str = ""
) -> Dict[str, Any]:
    is_exceeded = False
    diff = 0.0
    pct = 0.0
    
    unit_str = f" {unit}" if unit else ""
    
    if comparison_type == "greater_than":
        is_exceeded = reading_value > limit_value
        diff = reading_value - limit_value
        pct = (diff / limit_value * 100.0) if limit_value != 0 else 0.0
        
        if is_exceeded:
            summary = f"Exceedance detected: Reading ({reading_value}{unit_str}) is greater than SOP limit ({limit_value}{unit_str}) by {round(diff, 2)}{unit_str} ({round(pct, 2)}%)."
        else:
            summary = f"Normal operation: Reading ({reading_value}{unit_str}) is within SOP limit ({limit_value}{unit_str})."
            diff = 0.0
            pct = 0.0
            
    elif comparison_type == "less_than":
        is_exceeded = reading_value < limit_value
        diff = limit_value - reading_value
        pct = (diff / limit_value * 100.0) if limit_value != 0 else 0.0
        
        if is_exceeded:
            summary = f"Exceedance detected: Reading ({reading_value}{unit_str}) is less than SOP limit ({limit_value}{unit_str}) by {round(diff, 2)}{unit_str} ({round(pct, 2)}%)."
        else:
            summary = f"Normal operation: Reading ({reading_value}{unit_str}) is within SOP limit ({limit_value}{unit_str})."
            diff = 0.0
            pct = 0.0
    else:
        raise ValueError(f"Invalid comparison type: {comparison_type}")

    return {
        "is_exceeded": is_exceeded,
        "difference": round(diff, 4),
        "percentage_exceeded": round(pct, 4),
        "summary": summary
    }


def compute_variance_across_readings(readings: List[float]) -> Dict[str, Any]:
    n = len(readings)
    if n > 10000:
        raise ValueError("Too many readings. The maximum allowed size is 10,000 readings.")
    if n == 0:
        raise ValueError("Cannot calculate statistics on an empty list of readings.")
        
    mean = sum(readings) / n
    v_min = min(readings)
    v_max = max(readings)
    v_range = v_max - v_min
    
    if n > 1:
        variance = sum((x - mean) ** 2 for x in readings) / (n - 1)
        std_dev = math.sqrt(variance)
    else:
        variance = 0.0
        std_dev = 0.0

    return {
        "count": n,
        "mean": round(mean, 4),
        "min": round(v_min, 4),
        "max": round(v_max, 4),
        "range": round(v_range, 4),
        "variance": round(variance, 4),
        "std_dev": round(std_dev, 4),
        "summary": f"Analyzed {n} readings. Mean: {round(mean, 2)}, Min: {round(v_min, 2)}, Max: {round(v_max, 2)}, StdDev: {round(std_dev, 2)}."
    }


def convert_units(value: float, from_unit: str, to_unit: str) -> Dict[str, Any]:
    from_u = from_unit.strip()
    to_u = to_unit.strip()
    
    if from_u == to_u:
        return {
            "converted_value": value,
            "summary": f"No conversion needed: {value} {to_u}"
        }
        
    # Temperature Conversions
    temp_units = {"C", "F", "K"}
    if from_u in temp_units and to_u in temp_units:
        # Convert to Celsius first
        if from_u == "C":
            c_val = value
        elif from_u == "F":
            c_val = (value - 32.0) * 5.0 / 9.0
        else:  # K
            c_val = value - 273.15
            
        # Convert from Celsius to target
        if to_u == "C":
            res = c_val
        elif to_u == "F":
            res = (c_val * 9.0 / 5.0) + 32.0
        else:  # K
            res = c_val + 273.15
            
        return {
            "converted_value": round(res, 4),
            "summary": f"Converted {value} {from_u} to {round(res, 2)} {to_u}."
        }
        
    # Pressure Conversions (Standardized to Pascal)
    pressure_factors = {
        "pa": 1.0,
        "kpa": 1000.0,
        "mpa": 1000000.0,
        "bar": 100000.0,
        "psi": 6894.757
    }
    
    if from_u in pressure_factors and to_u in pressure_factors:
        # Convert to Pascal
        pa_val = value * pressure_factors[from_u]
        # Convert to target
        res = pa_val / pressure_factors[to_u]
        return {
            "converted_value": round(res, 4),
            "summary": f"Converted {value} {from_u} to {round(res, 4)} {to_u}."
        }
        
    raise ValueError(f"Incompatible units or unsupported conversion: from '{from_unit}' to '{to_unit}'")


def verify_engineering_calculation(text_input: str) -> Dict[str, Any]:
    from app.tools.calculation_verifier import extract_and_verify_calculation
    return extract_and_verify_calculation(text_input)


def evaluate_arithmetic_expression(expression: str) -> Dict[str, Any]:
    from app.tools.calculation_verifier import verify_calculation
    return verify_calculation(formula=expression, variables={})


# Singleton instance
tool_registry = LocalToolRegistry()

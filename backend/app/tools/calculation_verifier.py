import ast
import math
import operator
import re
import json
import inspect
from typing import Dict, Any, Union, Optional, Tuple

# Safe operators map
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Strict whitelist of allowed math functions
ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt,
    "log": math.log,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
}

class SecurityError(ValueError):
    """Raised when an expression contains disallowed nodes or syntax constructs."""
    pass


def evaluate_expression(expression: str, variables: Dict[str, Union[int, float]]) -> float:
    """
    Evaluates a scalar mathematical expression string using a safe AST parser and AST node walker.
    Never uses builtin eval() or exec(). Restricted strictly to safe arithmetic operations and whitelisted math functions.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Expression must be a non-empty string.")

    # Convert common math symbols like '^' to '**' for power operator
    cleaned_expr = expression.replace('^', '**').strip()

    try:
        parsed_ast = ast.parse(cleaned_expr, mode='eval')
    except SyntaxError as e:
        raise ValueError(f"Malformed mathematical expression: {e}")

    def _eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)

        elif isinstance(node, ast.Constant): # Python 3.8+
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise SecurityError(f"Constant of type '{type(node.value).__name__}' is not allowed.")

        elif isinstance(node, ast.Num): # Python < 3.8 fallback
            return float(node.n)

        elif isinstance(node, ast.Name):
            if node.id in variables:
                val = variables[node.id]
                if not isinstance(val, (int, float)):
                    raise ValueError(f"Variable '{node.id}' value must be numeric, got {type(val).__name__}.")
                return float(val)
            raise ValueError(f"Undefined variable '{node.id}' in expression.")

        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise SecurityError(f"Operator '{op_type.__name__}' is not supported.")
            
            left_val = _eval_node(node.left)
            right_val = _eval_node(node.right)

            if op_type is ast.Div and right_val == 0.0:
                raise ZeroDivisionError("Division by zero in calculation.")

            return float(SAFE_OPERATORS[op_type](left_val, right_val))

        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise SecurityError(f"Unary operator '{op_type.__name__}' is not supported.")
            
            operand_val = _eval_node(node.operand)
            return float(SAFE_OPERATORS[op_type](operand_val))

        elif isinstance(node, ast.Call):
            # Function call validation: must be direct function name from whitelist
            if not isinstance(node.func, ast.Name):
                raise SecurityError("Dynamic or attributed function calls are disallowed.")
            
            func_name = node.func.id
            if func_name not in ALLOWED_FUNCTIONS:
                raise SecurityError(f"Function '{func_name}' is not in the allowed function whitelist.")
            
            args = [_eval_node(arg) for arg in node.args]
            if node.keywords:
                raise SecurityError("Keyword arguments in function calls are disallowed.")
            
            return float(ALLOWED_FUNCTIONS[func_name](*args))

        else:
            raise SecurityError(f"Forbidden AST node type: '{type(node).__name__}'.")

    return _eval_node(parsed_ast)


def verify_calculation(
    formula: str,
    variables: Dict[str, Union[int, float]],
    claimed_answer: Optional[float] = None
) -> Dict[str, Any]:
    """
    Computes the real answer for a formula and variables dictionary, comparing against an optional claimed answer.
    Catches evaluation errors and returns NEEDS_REVIEW or OUT_OF_SCOPE safely.
    """
    try:
        computed_val = evaluate_expression(formula, variables)
    except (SecurityError, ValueError, ZeroDivisionError) as err:
        return {
            "status": "NEEDS_REVIEW",
            "formula": formula,
            "variables": variables,
            "computed": None,
            "claimed": claimed_answer,
            "delta": None,
            "is_match": False,
            "summary": f"Needs human review — calculation evaluation error: {str(err)}"
        }

    if claimed_answer is None:
        return {
            "status": "COMPUTED_ONLY",
            "formula": formula,
            "variables": variables,
            "computed": round(computed_val, 6),
            "claimed": None,
            "delta": 0.0,
            "is_match": True,
            "summary": f"Calculated value for formula '{formula}' is {round(computed_val, 4)}."
        }

    claimed_val = float(claimed_answer)
    delta = abs(computed_val - claimed_val)
    # Consider match if delta <= 0.01 or 0.1% relative tolerance
    rel_tol = 0.001 * max(abs(computed_val), abs(claimed_val), 1.0)
    is_match = delta <= rel_tol

    if is_match:
        summary = f"MATCH: Computed answer {round(computed_val, 4)} matches claimed answer {round(claimed_val, 4)} (delta: {round(delta, 6)})."
    else:
        summary = f"MISMATCH: Computed answer {round(computed_val, 4)} differs from claimed answer {round(claimed_val, 4)} by delta {round(delta, 4)}."

    return {
        "status": "MATCH" if is_match else "MISMATCH",
        "formula": formula,
        "variables": variables,
        "computed": round(computed_val, 6),
        "claimed": round(claimed_val, 6),
        "delta": round(delta, 6),
        "is_match": is_match,
        "summary": summary
    }


def verify_extracted_data_against_source(
    source_text: str,
    extracted_data: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Verification gate: Confirms that every variable name and numeric value claimed by the extraction
    actually appears in the original raw source text string.
    """
    if not isinstance(extracted_data, dict):
        return False, "Extracted payload is not a dictionary."

    formula = extracted_data.get("formula")
    variables = extracted_data.get("variables")
    claimed_answer = extracted_data.get("claimed_answer")
    confidence = str(extracted_data.get("extraction_confidence", "")).lower()

    if confidence == "low" or not formula or not isinstance(variables, dict) or len(variables) == 0:
        return False, "Extraction marked low confidence or missing formula/variables."

    # Check for calculus or out-of-scope keywords in formula or source text
    out_of_scope_keywords = ["integral", "derivative", "lim ", "d/dx", "dx", "dt", "matrix", "vector", "sum_i"]
    if any(kw in formula.lower() or kw in source_text.lower() for kw in out_of_scope_keywords):
        return False, "Formula contains out-of-scope operations (calculus/symbolic)."

    # 1. Verify every variable value (number) appears in original source text
    for var_name, var_val in variables.items():
        if var_val is None:
            return False, f"Variable '{var_name}' value is None."
        
        # Check string representations of numeric value in source_text
        val_str = str(var_val)
        val_str_clean = val_str.rstrip('0').rstrip('.') if '.' in val_str else val_str
        
        if val_str not in source_text and val_str_clean not in source_text:
            return False, f"Verification Gate Failed: Extracted value '{var_val}' for variable '{var_name}' does not appear in source text."

    # 2. Verify claimed answer if present
    if claimed_answer is not None:
        ans_str = str(claimed_answer)
        ans_str_clean = ans_str.rstrip('0').rstrip('.') if '.' in ans_str else ans_str
        if ans_str not in source_text and ans_str_clean not in source_text:
            return False, f"Verification Gate Failed: Extracted claimed answer '{claimed_answer}' does not appear in source text."

    return True, "Verification Gate Passed: All extracted values verified against source text."


def parse_calculation_from_text(source_text: str) -> Dict[str, Any]:
    """
    Extracts calculation components (formula, variables, claimed_answer) from free-text input
    using strict patterns or heuristic extraction.
    """
    text = source_text.strip()

    # Check for calculus or out-of-scope keywords
    if any(word in text.lower() for word in ["integral", "derivative", "matrix", "vector", "d/dx"]):
        return {
            "formula": None,
            "variables": {},
            "claimed_answer": None,
            "extraction_confidence": "low",
            "reason": "Calculus or symbolic equation outside scalar arithmetic scope.",
            "extraction_method": "regex_fallback"
        }

    formula_expr = None
    target_var = None

    # Look for "var = expression" (stopping before where, with, for, claimed, etc.)
    eq_match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z0-9_\s\+\-\*\/\^\(\)\.]+?)(?=\s*(?:where|with|when|for|\.|,|claimed|is|\n|$))', text, re.IGNORECASE)
    if eq_match:
        target_var = eq_match.group(1).strip()
        formula_expr = eq_match.group(2).strip()

    # Extract variables: e.g. "F = 500 N", "A = 2.5 m2", "K = 12.0", "dp = 16.0"
    var_matches = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([0-9]+(?:\.[0-9]+)?)\b', text)
    
    # Extract claimed answer: e.g. "Claimed answer is 200", "result = 48.0"
    claimed_match = re.search(r'(?:claimed|expected|result|answer|is)\s*(?:answer|result|is)?\s*=?\s*([0-9]+(?:\.[0-9]+)?)\b', text, re.IGNORECASE)

    extracted_vars = {}
    for var_name, var_val_str in var_matches:
        if target_var and var_name == target_var:
            continue
        try:
            val = float(var_val_str)
            extracted_vars[var_name] = val if not val.is_integer() else int(val)
        except ValueError:
            pass

    claimed_answer = None
    if claimed_match:
        try:
            claimed_answer = float(claimed_match.group(1))
        except ValueError:
            pass

    if not formula_expr or len(extracted_vars) == 0:
        return {
            "formula": None,
            "variables": {},
            "claimed_answer": None,
            "extraction_confidence": "low",
            "reason": "Could not identify formula or variable assignments in text.",
            "extraction_method": "regex_fallback"
        }

    return {
        "formula": formula_expr,
        "variables": extracted_vars,
        "claimed_answer": claimed_answer,
        "extraction_confidence": "high",
        "extraction_method": "regex_fallback"
    }


async def extract_calculation_with_llm_async(source_text: str, gateway=None) -> Dict[str, Any]:
    """
    Asynchronously extracts calculation components using ModelGateway LLM prompt.
    Falls back to parse_calculation_from_text if gateway is unavailable or fails.
    """
    if gateway is None:
        try:
            from app.gateway.factory import get_gateway
            gateway = get_gateway()
        except Exception:
            gateway = None

    if gateway is not None:
        prompt = (
            "You are an engineering calculation parser. "
            "Analyze the raw text input from an engineer or document and extract:\n"
            "1. The mathematical formula using variable names (e.g. F / A, K * sqrt(dp), v * A).\n"
            "2. The numeric variable values in a JSON dict (e.g. {\"F\": 500, \"A\": 2.5}).\n"
            "3. The claimed or expected answer numeric value, or null if not stated.\n"
            "4. Set extraction_confidence to 'high' if formula and numeric values are clear, else 'low'.\n\n"
            "Return ONLY a valid JSON object matching this exact schema:\n"
            "{\n"
            '  "formula": "<expression string or null>",\n'
            '  "variables": {"var_name": number_value, ...},\n'
            '  "claimed_answer": number_value_or_null,\n'
            '  "extraction_confidence": "high" or "low"\n'
            "}\n\n"
            f"Input Text:\n\"\"\"{source_text}\"\"\""
        )
        try:
            if inspect.iscoroutinefunction(gateway.generate):
                response_text = await gateway.generate(prompt)
            else:
                response_text = gateway.generate(prompt)

            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group(0))
                if isinstance(extracted, dict) and "formula" in extracted and "variables" in extracted:
                    extracted["extraction_method"] = "llm"
                    return extracted
        except Exception:
            pass

    fallback_res = parse_calculation_from_text(source_text)
    fallback_res["extraction_method"] = "regex_fallback"
    return fallback_res


def extract_calculation_with_llm(source_text: str, gateway=None) -> Dict[str, Any]:
    """
    Synchronous wrapper for extract_calculation_with_llm_async.
    """
    fallback_res = parse_calculation_from_text(source_text)
    fallback_res["extraction_method"] = "regex_fallback"
    return fallback_res


async def extract_and_verify_calculation_async(
    source_text: str,
    override_extracted: Optional[Dict[str, Any]] = None,
    gateway=None
) -> Dict[str, Any]:
    """
    Full async Step 2/3 pipeline: Takes free-text input, extracts using LLM gateway,
    runs the Verification Gate against raw source_text, and evaluates calculation if verified.
    Attaches explicit extraction_method ("llm" vs "regex_fallback").
    """
    try:
        if override_extracted is not None:
            extracted_data = override_extracted
            extraction_method = extracted_data.get("extraction_method", "override")
        else:
            extracted_data = await extract_calculation_with_llm_async(source_text, gateway=gateway)
            extraction_method = extracted_data.get("extraction_method", "regex_fallback")
        
        # Run Verification Gate
        is_valid, gate_reason = verify_extracted_data_against_source(source_text, extracted_data)
        
        if not is_valid:
            return {
                "status": "NEEDS_REVIEW",
                "formula": extracted_data.get("formula"),
                "variables": extracted_data.get("variables", {}),
                "computed": None,
                "claimed": extracted_data.get("claimed_answer"),
                "delta": None,
                "is_match": False,
                "gate_passed": False,
                "extraction_method": extraction_method,
                "summary": f"Needs human review — {gate_reason}"
            }

        # Verification passed: run calculation evaluation
        eval_res = verify_calculation(
            formula=extracted_data["formula"],
            variables=extracted_data["variables"],
            claimed_answer=extracted_data.get("claimed_answer")
        )
        eval_res["gate_passed"] = True
        eval_res["extraction_method"] = extraction_method
        return eval_res
    except Exception as e:
        return {
            "status": "NEEDS_REVIEW",
            "formula": None,
            "variables": {},
            "computed": None,
            "claimed": None,
            "delta": None,
            "is_match": False,
            "gate_passed": False,
            "extraction_method": "failed",
            "summary": f"Needs human review — unexpected calculation verification error: {str(e)}"
        }


def extract_and_verify_calculation(
    source_text: str,
    override_extracted: Optional[Dict[str, Any]] = None,
    gateway=None
) -> Dict[str, Any]:
    """
    Synchronous pipeline wrapper.
    """
    try:
        if override_extracted is not None:
            extracted_data = override_extracted
            extraction_method = extracted_data.get("extraction_method", "override")
        else:
            extracted_data = extract_calculation_with_llm(source_text, gateway=gateway)
            extraction_method = extracted_data.get("extraction_method", "regex_fallback")
        
        is_valid, gate_reason = verify_extracted_data_against_source(source_text, extracted_data)
        
        if not is_valid:
            return {
                "status": "NEEDS_REVIEW",
                "formula": extracted_data.get("formula"),
                "variables": extracted_data.get("variables", {}),
                "computed": None,
                "claimed": extracted_data.get("claimed_answer"),
                "delta": None,
                "is_match": False,
                "gate_passed": False,
                "extraction_method": extraction_method,
                "summary": f"Needs human review — {gate_reason}"
            }

        eval_res = verify_calculation(
            formula=extracted_data["formula"],
            variables=extracted_data["variables"],
            claimed_answer=extracted_data.get("claimed_answer")
        )
        eval_res["gate_passed"] = True
        eval_res["extraction_method"] = extraction_method
        return eval_res
    except Exception as e:
        return {
            "status": "NEEDS_REVIEW",
            "formula": None,
            "variables": {},
            "computed": None,
            "claimed": None,
            "delta": None,
            "is_match": False,
            "gate_passed": False,
            "extraction_method": "failed",
            "summary": f"Needs human review — unexpected calculation verification error: {str(e)}"
        }

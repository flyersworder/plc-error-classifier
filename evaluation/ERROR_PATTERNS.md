# Error Patterns & Synthetic Data Generation

This document captures our research on PLC compilation error patterns and the strategy
for generating synthetic test cases.

---

## Build Pipeline Stages

Errors can occur at any of these 4 stages:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ xml_validation  │────▶│ code_generation │────▶│ iec_compilation │────▶│ c_compilation   │
│                 │     │                 │     │                 │     │                 │
│ PLCopen XML     │     │ Beremiz Python  │     │ matiec/iec2c    │     │ gcc             │
│ schema check    │     │ code generator  │     │ ST → C compiler │     │ C → binary      │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Stage 1: XML Validation

**Source**: PLCopen XML schema validation (tc6_xml_v201.xsd)
**Error indicator**: "PLC XML file doesn't follow XSD schema"

From sample data:
```
Warning: PLC XML file doesn't follow XSD schema at line 61:
Element '{http://www.plcopen.org/xml/tc6_0201}data': Missing child element(s).
```

See [Error Patterns: XML Validation](#error-patterns-xml-validation) below.

### Stage 2: Code Generation

**Source**: Beremiz Python code (PLCGenerator.py, ProjectController.py)
**Error indicator**: Python traceback with `/root/beremiz/` paths

From sample data (`empty_project.txt`):
```
File "/root/beremiz/PLCGenerator.py", line 959, in ComputeProgram
    self.ParentGenerator.GeneratePouProgramInText(text.upper())
AttributeError: 'NoneType' object has no attribute 'upper'
```

See [Error Patterns: Code Generation](#error-patterns-code-generation-beremiz) below.

### Stage 3: IEC Compilation

**Source**: matiec/iec2c compiler
**Error indicator**: `iec2c` in path, "IEC to C compiler" messages

From sample data (`constant_error.txt`):
```
"/root/beremiz/matiec/iec2c" -f -l -p ...
Warning: error: Assignment to CONSTANT variables is not allowed.
```

See [Error Patterns: IEC Compilation](#error-patterns-iec-compilation-matiec) below.

### Stage 4: C Compilation

**Source**: gcc compiler
**Error indicator**: `gcc`, "undefined reference", linker errors

(No sample data for this stage - errors here are rare as generated C is usually valid)

See [Error Patterns: C Compilation](#error-patterns-c-compilation-gcc) below.

---

## Error Patterns: XML Validation

Source: [PLCopen TC6 XML Schema](https://www.plcopen.org/system/files/downloads/tc6_xml_v201_xsd.pdf)

### DateTime Format Errors

| Error Message | Trigger |
|---------------|---------|
| "'{value}' is not a valid value of the atomic type 'xs:dateTime'" | Wrong datetime format (space instead of 'T') |
| "Invalid datetime string for modificationDateTime" | Malformed modification timestamp |
| "Invalid datetime string for creationDateTime" | Malformed creation timestamp |

**Note**: Correct format is `2022-09-01T14:53:16`, not `2022-09-01 14:53:16`

### Element Structure Errors

| Error Message | Trigger |
|---------------|---------|
| "Missing child element(s). Expected is one of..." | Required child element missing |
| "Character content other than whitespace is not allowed" | Text in element-only content |
| "Element '{namespace}element': This element is not expected" | Unknown/invalid element |
| "Element '{namespace}element' is not complete" | Incomplete element definition |

### Attribute Errors

| Error Message | Trigger |
|---------------|---------|
| "The attribute '{name}' is required but missing" | Missing required attribute |
| "'{value}' is not a valid value for attribute '{name}'" | Invalid attribute value |
| "The attribute '{name}' is not allowed" | Unknown attribute |

### Namespace Errors

| Error Message | Trigger |
|---------------|---------|
| "No matching global declaration available" | Wrong namespace prefix |
| "Cannot resolve namespace prefix" | Undefined namespace |

---

## Error Patterns: Code Generation (Beremiz)

Source: [beremiz/PLCGenerator.py](https://github.com/nucleron/beremiz/blob/master/PLCGenerator.py)

### Python Runtime Errors (Traceback)

| Error Type | Trigger | Example |
|------------|---------|---------|
| `AttributeError: 'NoneType' object has no attribute 'upper'` | Empty program body | Empty `<ST><xhtml:p/></ST>` |
| `AttributeError: 'NoneType' object has no attribute '...'` | Missing required element | Null reference in generator |
| `KeyError: '...'` | Missing configuration | Undefined reference |
| `IndexError: list index out of range` | Empty list access | No POUs defined |

### PLCGenerator Explicit Errors

| Error Message | Trigger |
|---------------|---------|
| `"No body defined in \"{s}\" POU"` | POU has no body element |
| `"No variable defined in \"{s}\" POU"` | POU has no variable declarations |
| `"Undefined pou type \"{s}\""` | Invalid POU type attribute |
| `"Undefined block type \"{a1}\" in \"{a2}\" POU"` | Reference to unknown block |
| `"No informations found for \"{s}\" block"` | Block type not in library |

### Connector/Continuation Errors

| Error Message | Trigger |
|---------------|---------|
| `"No connector found corresponding to \"{a1}\" continuation in \"{a2}\" POU"` | Broken FBD/LD connection |
| `"More than one connector found corresponding to \"{a1}\" continuation in \"{a2}\" POU"` | Duplicate connector names |

### SFC (Sequential Function Chart) Errors

| Error Message | Trigger |
|---------------|---------|
| `"SFC transition in POU \"{s}\" must be connected"` | Unconnected transition |
| `"SFC jump in pou \"{a1}\" refers to non-existent SFC step \"{a2}\""` | Invalid jump target |
| `"Transition \"{s}\" body must contain an output variable or coil referring to its name"` | Missing transition output |
| `"Transition with content \"{a1}\" not connected to a previous step in \"{a2}\" POU"` | Broken transition chain |
| `"Transition with content \"{a1}\" not connected to a next step in \"{a2}\" POU"` | Broken transition chain |

### Function/FB Errors

| Error Message | Trigger |
|---------------|---------|
| `"\"{a1}\" function cancelled in \"{a2}\" POU: No input connected"` | Function missing required input |
| `"No output {a1} variable found in block {a2} in POU {a3}. Connection must be broken"` | Missing output variable |
| `"Source signal has to be defined for single task '{a1}' in resource '{a2}.{a3}'."` | Task configuration error |

### Build Process Errors

| Error Message | Trigger |
|---------------|---------|
| `"Runtime library extensions C code generation failed !\n"` | Extension code gen failure |
| `"Runtime IO extensions C code generation failed !\n"` | IO extension failure |
| `"C Build crashed !\n"` | Build process crash |

---

## Error Patterns: IEC Compilation (matiec)

Source: [matiec/stage3/print_datatypes_error.cc](https://github.com/nucleron/matiec)

### Data Type Range Errors

| Error Message | Trigger |
|---------------|---------|
| "Numerical value exceeds range for ANY_INT data type" | Integer overflow |
| "Numerical value exceeds range for ANY_REAL data type" | Float overflow |
| "Numerical value exceeds range for STRING data type" | String too long |
| "Numerical value exceeds range for %s data type" | Generic overflow |

### Data Type Mismatch Errors

| Error Message | Trigger |
|---------------|---------|
| "Incompatible data types for ':=' operation" | Assignment type mismatch |
| "Data type mismatch for '%s' operator" | Operator type mismatch |
| "Data type mismatch for '%s' expression" | Expression type mismatch |
| "Initial value has incompatible data type" | Wrong initializer type |
| "Data type incompatibility between parameter '%s' and value being passed" | Function arg mismatch |

### Variable Declaration Errors

| Error Message | Trigger |
|---------------|---------|
| "Variable not declared in this scope" | Undeclared variable |
| "Ambiguous enumerate value or Variable not declared in this scope" | Ambiguous reference |
| "Array variable not declared in this scope" | Undeclared array |
| "Undeclared structured (or FB) variable, or non-existant field" | Bad struct access |

### Syntax/Format Errors

| Error Message | Trigger |
|---------------|---------|
| "Invalid syntax for TIME data type" | Bad TIME literal |
| "Invalid syntax for DATE data type" | Bad DATE literal |
| "Invalid syntax for TOD data type" | Bad TOD literal |
| "Invalid syntax for DT data type" | Bad DT literal |
| "Invalid data type" | Generic invalid type |

### Control Flow Errors

| Error Message | Trigger |
|---------------|---------|
| "Invalid data type for 'IF' condition (should be BOOL)" | Non-BOOL in IF |
| "Invalid data type for 'ELSIF' condition (should be BOOL)" | Non-BOOL in ELSIF |
| "Invalid data type for 'WHILE' condition" | Non-BOOL in WHILE |
| "Invalid data type for 'REPEAT' condition" | Non-BOOL in REPEAT |
| "'CASE' quantity not an integer or enumerated" | Bad CASE expression |

### FOR Loop Errors

| Error Message | Trigger |
|---------------|---------|
| "Invalid data type for 'FOR' control variable" | Non-integer loop var |
| "Invalid data type for 'FOR' begin expression" | Bad start value |
| "Invalid data type for 'FOR' end expression" | Bad end value |
| "Invalid data type for 'FOR' by expression" | Bad step value |

### Function/FB Call Errors

| Error Message | Trigger |
|---------------|---------|
| "Duplicate parameter '%s' when invoking %s '%s'" | Repeated parameter |
| "Invalid parameter '%s' when invoking %s '%s'" | Unknown parameter |
| "Missing operand for FB call operator '%s'" | Missing FB operand |
| "Invalid FB call: operand is not a FB instance" | Wrong FB type |
| "Unable to resolve which overloaded %s '%s' is being invoked" | Ambiguous overload |
| "Invalid parameters when invoking %s '%s'" | Bad parameters |

### Assignment Errors

| Error Message | Trigger |
|---------------|---------|
| "Invalid assignment syntax ':=' used for parameter '%s'" | Wrong := usage |
| "Invalid assignment syntax '=>' used for parameter '%s'" | Wrong => usage |
| "Assignment to CONSTANT variables is not allowed" | Const assignment |

### Array/Subscript Errors

| Error Message | Trigger |
|---------------|---------|
| "Invalid data type for array subscript field" | Non-integer index |
| "Bit size of data type is incompatible with bit size of location" | Bit size mismatch |

### IL (Instruction List) Specific Errors

| Error Message | Trigger |
|---------------|---------|
| "Missing operand for %s operator" | Missing IL operand |
| "'NOT' operator may not have an operand" | Extra NOT operand |
| "%s operator must be preceded by an IL instruction producing a BOOL value" | Bad IL sequence |
| "Result of '%s' operation is never used" | Unused result |

### Reference/Pointer Errors

| Error Message | Trigger |
|---------------|---------|
| "^ operator must be preceded by a value of type REF_TO" | Bad dereference |
| "DREF operator must be used with a value of type REF_TO" | Bad DREF |
| "REF operator must be used with a variable" | REF on non-variable |

### Other Errors

| Error Message | Trigger |
|---------------|---------|
| "Invalid data type for 'NEG' expression" | Bad negation |
| "Invalid data type for 'NOT' expression" | Bad NOT |
| "Transition condition has invalid data type (should be BOOL)" | Bad SFC transition |
| "Deprecated operation for '%s' operator" | Deprecated usage |

---

## Error Patterns: C Compilation (gcc)

Source: [GCC Error Messages](https://gcc.gnu.org/onlinedocs/gcc/Warnings-and-Errors.html), [Common GCC Errors](https://labex.io/tutorials/c-how-to-handle-common-gcc-compilation-errors-430988)

**Note**: C compilation errors are rare in this pipeline since the C code is auto-generated
by matiec. When they occur, it's usually due to:
- Missing runtime libraries
- Platform-specific issues
- Bugs in matiec code generation

### Syntax Errors

| Error Message | Trigger |
|---------------|---------|
| `"error: expected ';' before '...'"` | Missing semicolon |
| `"error: expected ')' before '...'"` | Unbalanced parentheses |
| `"error: unterminated string or character constant"` | Unclosed string |
| `"error: stray '\\' in program"` | Invalid escape character |

### Declaration Errors

| Error Message | Trigger |
|---------------|---------|
| `"error: '...' undeclared (first use in this function)"` | Undeclared variable |
| `"warning: implicit declaration of function '...'"` | Missing function prototype |
| `"error: unknown type name '...'"` | Undefined type |
| `"error: conflicting types for '...'"` | Type redefinition mismatch |

### Linker Errors

| Error Message | Trigger |
|---------------|---------|
| `"undefined reference to '...'"` | Missing function definition |
| `"undefined reference to 'main'"` | Missing main function |
| `"undefined reference to 'sqrt'"` | Missing math library (-lm) |
| `"multiple definition of '...'"` | Duplicate symbol |
| `"ld returned 1 exit status"` | Linker failure |

### Type Errors

| Error Message | Trigger |
|---------------|---------|
| `"warning: comparison between pointer and integer"` | Type mismatch in comparison |
| `"error: incompatible types when assigning"` | Assignment type mismatch |
| `"warning: passing argument ... makes pointer from integer"` | Wrong argument type |
| `"error: subscripted value is neither array nor pointer"` | Invalid subscript |

### Include/Header Errors

| Error Message | Trigger |
|---------------|---------|
| `"fatal error: ...: No such file or directory"` | Missing header file |
| `"error: #include expects \"FILENAME\" or <FILENAME>"` | Malformed include |

---

## Synthesis Strategy

### Approach: LLM-Based Generation

We use a small LLM (Claude Haiku or GPT-4o-mini) to generate synthetic test cases.

**Why LLM-based?**
- More flexible than templates
- Can generate realistic variations
- Understands IEC 61131-3 semantics
- Cost-efficient (~$0.02 for 30 test cases)

### Inputs to Synthesizer

1. **Real error patterns from all 4 stages**:
   - XML Validation: ~15 patterns (datetime, element, attribute, namespace)
   - Code Generation: ~20 patterns (Python errors, PLCGenerator messages)
   - IEC Compilation: ~65 patterns (matiec type/syntax/control flow errors)
   - C Compilation: ~15 patterns (gcc syntax/linker/type errors)
2. **Base examples** (constant_error, empty_project from sample_data/)
3. **IEC 61131-3 ST syntax** (embedded in prompt)
4. **PLCopen XML structure** (embedded in prompt)

### Outputs per Test Case

```python
{
    "id": "test_001",
    "name": "for_loop_invalid_control_var",
    "description": "FOR loop with REAL control variable instead of INT",

    # Generated content
    "error_log": "...",      # Synthetic build output
    "source_xml": "...",     # PLCopen XML that causes the error

    # Ground truth labels
    "expected": {
        "severity": "blocking",
        "stage": "iec_compilation",
        "complexity": "trivial"
    },

    # Metadata
    "error_category": "for_loop",
    "base_pattern": "Invalid data type for 'FOR' control variable"
}
```

### Coverage Goals

Target: **20-30 test cases** covering:

| Stage | Target Count | Priority Patterns |
|-------|--------------|-------------------|
| xml_validation | 3-5 | Schema errors, missing elements |
| code_generation | 3-5 | NoneType, AttributeError, empty body |
| iec_compilation | 12-18 | Type mismatch, undeclared vars, control flow |
| c_compilation | 2-4 | Undefined reference, linker errors |

### Complexity Distribution

| Complexity | Count | Criteria |
|------------|-------|----------|
| trivial | 10-12 | Single error, obvious fix (typo, missing declaration) |
| moderate | 8-12 | Requires understanding context (type system, scope) |
| complex | 3-5 | Multiple errors, cascading issues, architectural problems |

### Severity Distribution

| Severity | Count | Criteria |
|----------|-------|----------|
| blocking | 15-20 | Build fails, cannot continue |
| warning | 5-8 | Build succeeds but with warnings |
| info | 2-4 | Informational messages, style issues |

---

## Labeling Rules

To ensure consistent ground truth labels, we define explicit rules:

### Severity Rules

```
blocking:
  - Any "error:" message
  - Python traceback (AttributeError, etc.)
  - "Cannot build project"
  - Compiler exit code != 0

warning:
  - Any "Warning:" that doesn't prevent build
  - Deprecated usage warnings
  - Schema validation warnings that don't stop build

info:
  - Build progress messages
  - Timing information
  - Non-critical notices
```

### Stage Detection Rules

```
xml_validation:
  - "XSD schema"
  - "XML file doesn't follow"
  - Schema namespace errors

code_generation:
  - Python traceback with "/beremiz/" paths
  - "PLCGenerator", "ProjectController" in stack
  - "Generating SoftPLC" followed by Python error

iec_compilation:
  - "iec2c" in command or path
  - "IEC to C compiler"
  - "matiec" in path
  - Error format: "filename:line-col..line-col: error:"

c_compilation:
  - "gcc" in command
  - "undefined reference"
  - "ld returned" (linker)
  - ".c:" or ".h:" in error path
```

### Complexity Rules

```
trivial:
  - Single error instance
  - Fix is a one-line change
  - Error message clearly states the problem
  - Examples: typo, missing semicolon, wrong type literal

moderate:
  - Requires understanding variable scope or type system
  - May need to check multiple locations
  - Fix requires understanding the intent
  - Examples: type mismatch, undeclared variable in nested scope

complex:
  - Multiple related errors (cascading)
  - Requires architectural understanding
  - May need to restructure code
  - Examples: circular dependencies, wrong FB usage pattern
```

---

## Implementation Status

### Completed

1. [x] Create synthesizer prompt with error patterns → `evaluation/generator.py`
2. [x] Define 21 error patterns covering all 4 stages
3. [x] Implement LLM-as-judge for suggestion quality → `evaluation/judge.py`
4. [x] Implement evaluation runner and metrics → `evaluation/run_eval.py`, `evaluation/metrics.py`
5. [x] Define complexity heuristics → `evaluation/models.py`

### Remaining

1. [ ] Generate 20-30 test cases using `SyntheticTestGenerator`
2. [ ] Manual review of generated cases for quality
3. [ ] Run full evaluation and generate report

### Usage

```bash
# Generate test cases
uv run python -m evaluation.generator

# Run evaluation
uv run python -m evaluation.run_eval

# Or programmatically
from evaluation import SyntheticTestGenerator, EvaluationRunner
```

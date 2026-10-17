using Mono.Cecil;
using Mono.Cecil.Cil;

namespace RoR2DedicatedPatcher;

// Control-flow stack-depth verification, including unreachable blocks and EH entries.
// This is not a replacement for Unity/Mono execution or a full CLR type verifier.
internal static class ILSafety
{
    internal static void NormalizeAndVerify(MethodDefinition method)
    {
        foreach (var instruction in method.Body.Instructions)
            instruction.OpCode = instruction.OpCode.Code switch {
                Code.Br_S => OpCodes.Br, Code.Brfalse_S => OpCodes.Brfalse, Code.Brtrue_S => OpCodes.Brtrue,
                Code.Beq_S => OpCodes.Beq, Code.Bge_S => OpCodes.Bge, Code.Bge_Un_S => OpCodes.Bge_Un,
                Code.Bgt_S => OpCodes.Bgt, Code.Bgt_Un_S => OpCodes.Bgt_Un,
                Code.Ble_S => OpCodes.Ble, Code.Ble_Un_S => OpCodes.Ble_Un,
                Code.Blt_S => OpCodes.Blt, Code.Blt_Un_S => OpCodes.Blt_Un,
                Code.Bne_Un_S => OpCodes.Bne_Un, Code.Leave_S => OpCodes.Leave,
                _ => instruction.OpCode
            };
        var instructions = method.Body.Instructions;
        if (instructions.Count == 0) throw new InvalidOperationException($"Empty method: {method.FullName}");
        var members = instructions.ToHashSet();
        var depths = new Dictionary<Instruction, int>();
        var pending = new Queue<(Instruction Instruction, int Depth)>();
        void Enqueue(Instruction? instruction, int depth)
        {
            if (instruction == null || !members.Contains(instruction)) throw new InvalidOperationException($"Invalid control-flow target: {method.FullName}");
            pending.Enqueue((instruction, depth));
        }
        Enqueue(instructions[0], 0);
        foreach (var handler in method.Body.ExceptionHandlers)
        {
            Enqueue(handler.HandlerStart, handler.HandlerType is ExceptionHandlerType.Catch or ExceptionHandlerType.Filter ? 1 : 0);
            if (handler.FilterStart != null) Enqueue(handler.FilterStart, 1);
        }
        int maximum = 0;
        void Drain()
        {
            while (pending.TryDequeue(out var item))
            {
                var (instruction, depth) = item;
                if (depths.TryGetValue(instruction, out int prior))
                {
                    if (prior != depth) throw new InvalidOperationException($"IL stack merge mismatch at {instruction}: {prior} versus {depth} in {method.FullName}");
                    continue;
                }
                depths.Add(instruction, depth);
                maximum = Math.Max(maximum, depth);
                int pop = Pop(instruction, method, depth);
                if (depth < pop) throw new InvalidOperationException($"IL stack underflow at {instruction} in {method.FullName}");
                int after = depth - pop + Push(instruction);
                maximum = Math.Max(maximum, after);
                if (instruction.OpCode.Code is Code.Ret or Code.Throw or Code.Rethrow or Code.Endfinally or Code.Endfilter or Code.Jmp)
                {
                    if (after != 0) throw new InvalidOperationException($"IL terminal stack is not empty at {instruction} in {method.FullName}");
                    continue;
                }
                if (instruction.OpCode.FlowControl == FlowControl.Branch)
                    Enqueue(instruction.Operand as Instruction, after);
                else if (instruction.OpCode.FlowControl == FlowControl.Cond_Branch)
                {
                    if (instruction.Operand is Instruction target) Enqueue(target, after);
                    else if (instruction.Operand is Instruction[] targets) foreach (var targetInstruction in targets) Enqueue(targetInstruction, after);
                    else throw new InvalidOperationException("Invalid conditional branch operand.");
                    Enqueue(instruction.Next, after);
                }
                else Enqueue(instruction.Next, after);
            }
        }
        Drain();
        // Unity Mono rejects malformed unreachable instruction blocks too.
        foreach (var instruction in instructions) if (!depths.ContainsKey(instruction)) { Enqueue(instruction, 0); Drain(); }
        method.Body.MaxStackSize = Math.Max(method.Body.MaxStackSize, maximum);
    }
    private static int Pop(Instruction instruction, MethodDefinition method, int depth)
    {
        var behaviour = instruction.OpCode.StackBehaviourPop;
        if (behaviour == StackBehaviour.PopAll) return depth;
        if (behaviour == StackBehaviour.Pop0) return 0;
        if (behaviour == StackBehaviour.Varpop)
        {
            if (instruction.OpCode.Code == Code.Ret) return method.ReturnType.MetadataType == MetadataType.Void ? 0 : 1;
            if (instruction.Operand is MethodReference called) return called.Parameters.Count + (instruction.OpCode.Code != Code.Newobj && called.HasThis ? 1 : 0);
            if (instruction.Operand is CallSite site) return site.Parameters.Count + (site.HasThis ? 1 : 0) + 1;
            throw new InvalidOperationException($"Unsupported variable-pop opcode {instruction.OpCode}");
        }
        return behaviour.ToString().Split('_').Length;
    }
    private static int Push(Instruction instruction)
    {
        var behaviour = instruction.OpCode.StackBehaviourPush;
        if (behaviour == StackBehaviour.Push0) return 0;
        if (behaviour == StackBehaviour.Varpush)
        {
            if (instruction.OpCode.Code == Code.Newobj) return 1;
            var returns = instruction.Operand switch { MethodReference method => method.ReturnType, CallSite site => site.ReturnType, _ => throw new InvalidOperationException("Unsupported variable-push opcode.") };
            return returns.MetadataType == MetadataType.Void ? 0 : 1;
        }
        return behaviour == StackBehaviour.Push1_push1 ? 2 : 1;
    }
}

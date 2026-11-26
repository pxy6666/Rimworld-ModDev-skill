using System.Collections.Immutable;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

// Read bytes and static PE metadata. Never load or execute the inspected assemblies.
if (args.Length != 2 || args[1] is not ("decl" or "refs")) return 2;
try { Probe.Run(args[0], args[1] == "refs"); return 0; }
catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }

static class Probe {
    sealed record Operand(string Assembly, string Version, string Type, string Name, string Key, string Kind);
    static readonly Dictionary<ushort, OpCode> Opcodes = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
        .Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!)
        .GroupBy(op => (ushort)op.Value).ToDictionary(g => g.Key, g => g.First());

    public static void Run(string path, bool indexRefs) {
        var bytes = File.ReadAllBytes(path);
        using var stream = new MemoryStream(bytes, writable: false);
        using var pe = new PEReader(stream);
        var reader = pe.GetMetadataReader();
        var names = new Names();
        var assembly = reader.GetAssemblyDefinition();
        var asm = reader.GetString(assembly.Name);
        var version = assembly.Version.ToString();
        using var output = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false), 65536);
        void Emit(params object?[] parts) => output.WriteLine(JsonSerializer.Serialize(parts));
        Emit("header", asm, version, Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant());

        string? TypeName(EntityHandle h) => h.IsNil ? null : h.Kind switch {
            HandleKind.TypeDefinition => names.GetTypeFromDefinition(reader, (TypeDefinitionHandle)h, 0),
            HandleKind.TypeReference => names.GetTypeFromReference(reader, (TypeReferenceHandle)h, 0),
            HandleKind.TypeSpecification => names.GetTypeFromSpecification(reader, null, (TypeSpecificationHandle)h, 0),
            _ => null
        };
        bool EffectivePublic(TypeDefinitionHandle h) {
            var type = reader.GetTypeDefinition(h);
            var visibility = type.Attributes & TypeAttributes.VisibilityMask;
            return visibility == TypeAttributes.Public || (visibility == TypeAttributes.NestedPublic &&
                !type.GetDeclaringType().IsNil && EffectivePublic(type.GetDeclaringType()));
        }
        (string, string) Scope(EntityHandle h) {
            // For a constructed generic TypeSpec, the outer generic type identifies the scope.
            if (h.Kind == HandleKind.TypeSpecification) {
                var blob = reader.GetBlobReader(reader.GetTypeSpecification((TypeSpecificationHandle)h).Signature);
                if (blob.ReadSignatureTypeCode() != SignatureTypeCode.GenericTypeInstance ||
                    blob.ReadSignatureTypeCode() != SignatureTypeCode.TypeHandle) return ("", "");
                h = blob.ReadTypeHandle();
            }
            while (h.Kind == HandleKind.TypeReference)
                h = reader.GetTypeReference((TypeReferenceHandle)h).ResolutionScope;
            if (h.Kind == HandleKind.AssemblyReference) {
                var aref = reader.GetAssemblyReference((AssemblyReferenceHandle)h);
                return (reader.GetString(aref.Name), aref.Version.ToString());
            }
            return h.Kind is HandleKind.TypeDefinition or HandleKind.ModuleDefinition ? (asm, version) : ("", "");
        }
        static string MethodKey(string name, MethodSignature<string> sig) => MethodKeyWith(name, sig.GenericParameterCount, sig.ParameterTypes);
        static string MethodIdentity(string name, MethodSignature<string> sig) =>
            sig.Header.RawValue + ":" + sig.ReturnType + " " + MethodKey(name, sig);
        static string MethodKeyWith(string name, int arity, IEnumerable<string> parameters) =>
            name + (arity > 0 ? "``" + arity : "") + "(" + string.Join(", ", parameters) + ")";
        var targets = new Dictionary<EntityHandle, Operand?>();
        Operand? Target(EntityHandle h) {
            if (targets.TryGetValue(h, out var saved)) return saved;
            Operand? value = null;
            if (h.Kind == HandleKind.MethodSpecification) {
                value = Target(reader.GetMethodSpecification((MethodSpecificationHandle)h).Method);
            } else if (h.Kind == HandleKind.MemberReference) {
                var mr = reader.GetMemberReference((MemberReferenceHandle)h);
                var parent = mr.Parent;
                if (parent.Kind == HandleKind.MethodDefinition) parent = reader.GetMethodDefinition((MethodDefinitionHandle)parent).GetDeclaringType();
                var name = reader.GetString(mr.Name);
                var type = TypeName(parent);
                if (type != null) {
                    var (ta, tv) = Scope(parent);
                    // TypeSpec instantiation is not a separate declaring type.
                    if (parent.Kind == HandleKind.TypeSpecification) {
                        for (int i = 0; i < type.Length - 1; i++) {
                            if (type[i] != '`' || !char.IsAsciiDigit(type[i + 1])) continue;
                            int end = i + 2;
                            while (end < type.Length && char.IsAsciiDigit(type[end])) end++;
                            if (end < type.Length && type[end] == '<') { type = type[..end]; break; }
                        }
                    }
                    value = mr.GetKind() == MemberReferenceKind.Method
                        ? new(ta, tv, type, name, MethodIdentity(name, mr.DecodeMethodSignature(names, null)), "method")
                        : new(ta, tv, type, name, mr.DecodeFieldSignature(names, null) + " " + name, "field");
                }
            } else if (h.Kind == HandleKind.MethodDefinition) {
                var md = reader.GetMethodDefinition((MethodDefinitionHandle)h);
                var name = reader.GetString(md.Name);
                value = new(asm, version, TypeName(md.GetDeclaringType())!, name, MethodIdentity(name, md.DecodeSignature(names, null)), "method");
            } else if (h.Kind == HandleKind.FieldDefinition) {
                var fd = reader.GetFieldDefinition((FieldDefinitionHandle)h);
                var name = reader.GetString(fd.Name);
                value = new(asm, version, TypeName(fd.GetDeclaringType())!, name, fd.DecodeSignature(names, null) + " " + name, "field");
            }
            return targets[h] = value;
        }

        var scanErrors = 0;
        var scanned = 0;
        foreach (var th in reader.TypeDefinitions) {
            var t = reader.GetTypeDefinition(th);
            var type = TypeName(th)!;
            if (type == "<Module>") continue;
            Emit("type", type, reader.GetString(t.Name), TypeName(t.BaseType), t.Attributes.ToString(), EffectivePublic(th));
            foreach (var fh in t.GetFields()) {
                var f = reader.GetFieldDefinition(fh);
                var name = reader.GetString(f.Name);
                var signature = f.DecodeSignature(names, null) + " " + name;
                Emit("member", MetadataTokens.GetToken(fh), type, "field", name, signature, signature, name,
                     f.Attributes.ToString(), null);
            }
            foreach (var mh in t.GetMethods()) {
                var m = reader.GetMethodDefinition(mh);
                var sig = m.DecodeSignature(names, null);
                var name = reader.GetString(m.Name);
                var key = MethodIdentity(name, sig);
                var pars = m.GetParameters().Select(reader.GetParameter).Where(p => p.SequenceNumber > 0)
                    .ToDictionary(p => (int)p.SequenceNumber);
                var display = sig.ParameterTypes.Select((pt, i) => {
                    if (!pt.EndsWith('&')) return pt;
                    var flag = pars.TryGetValue(i + 1, out var p) ? p.Attributes : 0;
                    return (flag.HasFlag(ParameterAttributes.Out) ? "out " : flag.HasFlag(ParameterAttributes.In) ? "in " : "ref ") + pt[..^1];
                });
                var displayKey = MethodKeyWith(name, sig.GenericParameterCount, display);
                var token = MetadataTokens.GetToken(mh);
                var details = pars.Select(p => {
                    var c = p.Value.GetDefaultValue();
                    return new { position = p.Key, name = reader.GetString(p.Value.Name), flags = p.Value.Attributes.ToString(),
                        metadataDefault = c.IsNil ? null : new { type = reader.GetConstant(c).TypeCode.ToString(),
                            bytesHex = Convert.ToHexString(reader.GetBlobBytes(reader.GetConstant(c).Value)) } };
                }).ToArray();
                Emit("member", token, type, "method", name, sig.ReturnType + " " + displayKey, key, displayKey,
                     m.Attributes.ToString(), details);
                if (!indexRefs || m.RelativeVirtualAddress == 0 ||
                    (m.ImplAttributes & MethodImplAttributes.CodeTypeMask) != MethodImplAttributes.IL) continue;
                try {
                    var body = pe.GetMethodBody(m.RelativeVirtualAddress).GetILReader();
                    var operands = new Dictionary<(Operand, string), int>();
                    while (body.RemainingBytes > 0) {
                        ushort opval = body.ReadByte();
                        if (opval == 0xfe) opval = (ushort)(0xfe00 | body.ReadByte());
                        if (!Opcodes.TryGetValue(opval, out var op)) throw new BadImageFormatException("Unknown IL opcode");
                        var count = op.OperandType switch {
                            OperandType.InlineNone => 0,
                            OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
                            OperandType.InlineVar => 2,
                            OperandType.InlineBrTarget or OperandType.InlineI or OperandType.InlineSig or OperandType.InlineString or OperandType.InlineType or OperandType.ShortInlineR => 4,
                            OperandType.InlineI8 or OperandType.InlineR => 8,
                            _ => -1,
                        };
                        if (count >= 0) {
                            if (body.RemainingBytes < count) throw new BadImageFormatException("Truncated IL operand");
                            body.Offset += count;
                        } else if (op.OperandType == OperandType.InlineSwitch) {
                            var n = body.ReadInt32();
                            if (n < 0 || n > body.RemainingBytes / 4) throw new BadImageFormatException("Invalid IL switch");
                            body.Offset += n * 4;
                        } else if (op.OperandType is OperandType.InlineField or OperandType.InlineMethod or OperandType.InlineTok) {
                            var operand = Target(MetadataTokens.EntityHandle(body.ReadInt32()));
                            if (operand != null) {
                                var edge = (operand, op.Name!);
                                operands[edge] = operands.GetValueOrDefault(edge) + 1;
                            }
                        } else throw new BadImageFormatException("Unsupported IL operand type");
                    }
                    foreach (var ((operand, op), count) in operands)
                        Emit("ref", token, operand.Assembly, operand.Version, operand.Type, operand.Name, operand.Key, operand.Kind, op, count);
                    scanned++;
                } catch (Exception ex) when (ex is BadImageFormatException or ArgumentOutOfRangeException or InvalidOperationException) { scanErrors++; }
            }
        }
        Emit("done", scanned, scanErrors);
    }
}

sealed class Names : ISignatureTypeProvider<string, object?> {
    public string GetTypeFromDefinition(MetadataReader r, TypeDefinitionHandle h, byte _) {
        var t = r.GetTypeDefinition(h);
        return t.GetDeclaringType().IsNil ? Join(r.GetString(t.Namespace), r.GetString(t.Name)) : GetTypeFromDefinition(r, t.GetDeclaringType(), 0) + "+" + r.GetString(t.Name);
    }
    public string GetTypeFromReference(MetadataReader r, TypeReferenceHandle h, byte _) {
        var t = r.GetTypeReference(h);
        return t.ResolutionScope.Kind == HandleKind.TypeReference ? GetTypeFromReference(r, (TypeReferenceHandle)t.ResolutionScope, 0) + "+" + r.GetString(t.Name) : Join(r.GetString(t.Namespace), r.GetString(t.Name));
    }
    static string Join(string ns, string name) => ns.Length == 0 ? name : ns + "." + name;
    public string GetTypeFromSpecification(MetadataReader r, object? c, TypeSpecificationHandle h, byte _) => r.GetTypeSpecification(h).DecodeSignature(this, c);
    public string GetArrayType(string e, ArrayShape s) => e + "[" + new string(',', s.Rank - 1) + "]";
    public string GetByReferenceType(string e) => e + "&";
    public string GetFunctionPointerType(MethodSignature<string> s) => "fnptr:" + s.Header.CallingConvention + ":" + s.ReturnType + "(" + string.Join(",", s.ParameterTypes) + ")";
    public string GetGenericInstantiation(string t, ImmutableArray<string> a) => t + "<" + string.Join(",", a) + ">";
    public string GetGenericMethodParameter(object? c, int i) => "!!" + i;
    public string GetGenericTypeParameter(object? c, int i) => "!" + i;
    public string GetModifiedType(string m, string e, bool required) => e + (required ? " modreq(" : " modopt(") + m + ")";
    public string GetPinnedType(string e) => e + " pinned";
    public string GetPointerType(string e) => e + "*";
    public string GetPrimitiveType(PrimitiveTypeCode c) => c.ToString();
    public string GetSZArrayType(string e) => e + "[]";
}

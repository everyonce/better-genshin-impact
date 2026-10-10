using Microsoft.ClearScript;
using System;
using System.Reflection;

namespace BetterGenshinImpact.Core.Script.Dependence;

public class CustomHostFunctions : HostFunctions
{
    /// <summary>
    /// 创建指定维度的交错数组变量
    /// </summary>
    /// <typeparam name="T">数组元素类型</typeparam>
    /// <param name="dimensions">数组维度</param>
    /// <returns>交错数组变量</returns>
    public object NewVarOfArr<T>(int dimensions)
    {
        try
        {
            Type arrayType = typeof(T);
            for (int i = 0; i < dimensions; i++)
            {
                arrayType = arrayType.MakeArrayType();
            }

            MethodInfo newVarMethod = typeof(HostFunctions).GetMethod(nameof(newVar))!;
            MethodInfo genericMethod = newVarMethod.MakeGenericMethod(arrayType);
            return genericMethod.Invoke(this, new object?[] { null })!;
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException($"Failed to create an array with dimensions {dimensions}: {ex.Message}", ex);
        }
    }
}

using System;

namespace BetterGenshinImpact.GameTask.LogParse;

public class NoLoginException(string message = "Not logged in") : Exception(message)
{
}
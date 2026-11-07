using Microsoft.AspNetCore.Mvc;

public class PatternsController : ControllerBase
{
    [HttpPost("/v1/interpret")]
    public IActionResult Interpret([FromBody] InterpretRequest body)
    {
        // ruleid: api-security.identity-from-request.csharp
        var user = body.UserId;
        // ruleid: api-security.identity-from-request.csharp
        var device = Request.Query["deviceId"];
        // ruleid: api-security.identity-from-request.csharp
        var acct = Request.Headers["x-account-id"];
        // ok: api-security.identity-from-request.csharp
        var text = body.Text;
        // ok: api-security.identity-from-request.csharp
        var me = User.FindFirst("sub");
        return Ok(new { user, device, acct, text, me });
    }
}

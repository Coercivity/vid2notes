namespace Vid2Notes.Api.Contracts;

public record JobFailed(Guid JobId, string Stage, string Reason);

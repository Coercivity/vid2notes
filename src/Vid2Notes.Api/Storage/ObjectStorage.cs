using System.Net;
using Amazon.Runtime;
using Amazon.S3;
using Microsoft.Extensions.Options;

namespace Vid2Notes.Api.Storage;

public class ObjectStorage : IDisposable
{
    private readonly AmazonS3Client _client;
    private readonly string _bucket;

    public ObjectStorage(IOptions<StorageOptions> options)
    {
        var value = options.Value;
        _bucket = value.Bucket;
        _client = new AmazonS3Client(
            new BasicAWSCredentials(value.AccessKey, value.SecretKey),
            new AmazonS3Config
            {
                ServiceURL = value.Endpoint,
                ForcePathStyle = true,
                AuthenticationRegion = "us-east-1"
            });
    }

    public async Task<StoredObject?> OpenAsync(string key, CancellationToken cancellationToken)
    {
        try
        {
            var response = await _client.GetObjectAsync(_bucket, key, cancellationToken);
            return new StoredObject(response.ResponseStream, response.Headers.ContentType ?? "application/octet-stream");
        }
        catch (AmazonS3Exception e) when (e.StatusCode == HttpStatusCode.NotFound)
        {
            return null;
        }
    }

    public void Dispose() => _client.Dispose();
}

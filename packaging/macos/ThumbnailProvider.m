#import <ImageIO/ImageIO.h>
#import <QuickLookThumbnailing/QuickLookThumbnailing.h>

@interface HiFineThumbnailProvider : QLThumbnailProvider
@end

@implementation HiFineThumbnailProvider
- (void)provideThumbnailForFileRequest:(QLFileThumbnailRequest *)request
                     completionHandler:(void (^)(QLThumbnailReply *, NSError *))handler {
    CGSize box = request.maximumSize;
    CGFloat longestEdge = ceil(MAX(box.width, box.height) * request.scale);
    NSDictionary *options = @{
        (__bridge NSString *)kCGImageSourceCreateThumbnailFromImageIfAbsent: @YES,
        (__bridge NSString *)kCGImageSourceCreateThumbnailWithTransform: @YES,
        (__bridge NSString *)kCGImageSourceThumbnailMaxPixelSize: @(longestEdge)
    };
    CGImageSourceRef source = CGImageSourceCreateWithURL((__bridge CFURLRef)request.fileURL, NULL);
    CGImageRef thumbnail = source ? CGImageSourceCreateThumbnailAtIndex(
        source, CGImageSourceGetPrimaryImageIndex(source), (__bridge CFDictionaryRef)options) : NULL;
    if (source) CFRelease(source);
    if (!thumbnail) {
        handler(nil, [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileReadCorruptFileError userInfo:nil]);
        return;
    }

    CGFloat width = CGImageGetWidth(thumbnail);
    CGFloat height = CGImageGetHeight(thumbnail);
    CGFloat factor = MIN(box.width / width, box.height / height);
    CGSize size = CGSizeMake(width * factor, height * factor);
    // Quick Look calls this block after the request handler returns.
    id retainedImage = CFBridgingRelease(thumbnail);
    handler([QLThumbnailReply replyWithContextSize:size drawingBlock:^BOOL(CGContextRef context) {
        CGContextDrawImage(context, (CGRect){CGPointZero, size}, (__bridge CGImageRef)retainedImage);
        return YES;
    }], nil);
}
@end

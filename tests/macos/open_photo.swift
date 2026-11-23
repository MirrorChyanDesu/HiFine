import AppKit
import Foundation

// Exercise the same registered document-opening service used by Finder.
let bundle = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
let photo = URL(fileURLWithPath: CommandLine.arguments[2]).standardizedFileURL
let handlers = NSWorkspace.shared.urlsForApplications(toOpen: photo)
guard handlers.contains(where: { $0.standardizedFileURL.path == bundle.path }) else {
    fputs("Launch Services did not register HiFine as a viewer for this HIF.\n", stderr)
    exit(1)
}

var launched: NSRunningApplication?
var launchError: Error?
NSWorkspace.shared.open([photo], withApplicationAt: bundle,
                        configuration: NSWorkspace.OpenConfiguration()) { app, error in
    launched = app
    launchError = error
}
let deadline = Date().addingTimeInterval(30)
while Date() < deadline && launchError == nil && launched?.isFinishedLaunching != true {
    RunLoop.current.run(until: Date().addingTimeInterval(0.1))
}
guard let app = launched, !app.isTerminated, app.isFinishedLaunching else {
    fputs("Could not launch HiFine for the HIF file: \(String(describing: launchError))\n", stderr)
    exit(1)
}
print("Launch Services opened \(photo.lastPathComponent) with \(app.localizedName ?? bundle.lastPathComponent).")
app.terminate()

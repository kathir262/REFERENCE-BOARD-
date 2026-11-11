# RefPad uses no reflection or serialisation libraries, so R8's defaults are enough.
# Custom views used in XML layouts are kept automatically by the build.

# Keep line numbers in crash reports (Play Console can de-obfuscate them with mapping.txt).
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

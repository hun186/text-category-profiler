class PackageImporter:
    def proc():
        import sys
        import glob
        ModPaths = []
        #ModPaths.extend(glob.glob("C:/Users/*/Documents/PythonModule"))
        ModPaths.extend([
            "D:/shared/PythonModule",
            "Z:/PythonModule",
            "PythonModule",
            "../PythonModule",
            "../../PythonModule",
            "../../../PythonModule",
            "../../../../PythonModule",
            "../../../../../PythonModule",
            "../../../../../../PythonModule",
            "./../",
            "../../TopicClassification",
            "/mntCZJ/TopicClassification",
            "./",
            ".",
            #"D:\shared\TopicClassification",
            ])
        for ModulePath in ModPaths:
            sys.path.append(ModulePath)
        #print(sys.path)
        import os
source_file = [
   'tvgWebpLoader.h',
   'tvgWebpLoader.cpp',
]

webp_inc = include_directories(get_option('webp_include_dir'))
webp_lib = cc.find_library('webp', dirs: [get_option('webp_lib_dir')], required: true)
webp_dep = declare_dependency(
  include_directories: webp_inc,
  dependencies: [webp_lib]
)

if webp_dep.found()
   subloader_dep += [declare_dependency(
      include_directories : include_directories('.'),
      dependencies : webp_dep,
      sources : source_file
      )]
endif
